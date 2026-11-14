use crate::{
    rebuild,
    reflection::{self, ToolSelection},
};
use chrono::{DateTime, Timelike, Utc};
use chrono_tz::Tz;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

type Result<T> = std::result::Result<T, String>;
const MAX_BATCHES: u32 = 32;
const MAX_TOOLS: usize = 15;
const STATE: &str = "reflection-schedule.state.json";

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Stream {
    scope: String,
    route: String,
    entry: String,
    after: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Schedule {
    stream: Stream,
    timezone: Tz,
    hours: BTreeSet<u32>,
    #[serde(default)]
    include_tools: bool,
}

#[derive(Deserialize, Serialize)]
struct State {
    stream: Stream,
    timezone: Tz,
    cursor: u64,
    serial: u64,
    pending: Option<Pending>,
    cycle: Option<Cycle>,
}

#[derive(Deserialize, Serialize)]
#[serde(untagged)]
enum Pending {
    Event(u64),
    WithTools {
        event: u64,
        tools: Vec<ToolSelection>,
    },
}

impl Pending {
    fn event(&self) -> u64 {
        match self {
            Self::Event(event) | Self::WithTools { event, .. } => *event,
        }
    }

    fn tools(&self) -> &[ToolSelection] {
        match self {
            Self::Event(_) => &[],
            Self::WithTools { tools, .. } => tools,
        }
    }
}

#[derive(Deserialize, Serialize)]
struct Cycle {
    slot: String,
    completed: u32,
    outcome: Outcome,
}

#[derive(PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Outcome {
    Running,
    Foreground,
    Held,
    Drained,
    Limit,
}

impl Schedule {
    pub fn load(root: &Path) -> Result<Self> {
        let config: Self = rebuild::read_json(&root.join("reflection-schedule.json"))?
            .ok_or("missing reflection schedule")?;
        if config.hours.is_empty()
            || config.hours.iter().any(|&hour| hour >= 24)
            || !bounded(&config.stream.scope, 256)
            || !bounded(&config.stream.route, 128)
            || !bounded(&config.stream.entry, 256)
            || i64::try_from(config.stream.after).is_err()
        {
            return Err("invalid reflection schedule".into());
        }
        let _ = config.state(root)?;
        Ok(config)
    }

    fn state(&self, root: &Path) -> Result<State> {
        let state = rebuild::read_json::<State>(&root.join(STATE))?;
        match state {
            Some(state) if state.stream == self.stream && state.timezone == self.timezone => {
                Ok(state)
            }
            Some(_) => Err("original reflection stream changed".into()),
            None => Ok(State {
                stream: self.stream.clone(),
                timezone: self.timezone,
                cursor: self.stream.after,
                serial: 1,
                pending: None,
                cycle: None,
            }),
        }
    }

    pub fn poll(
        &self,
        root: &Path,
        now: DateTime<Utc>,
        mut call: impl FnMut(&str, Value) -> Result<Value>,
    ) -> Result<()> {
        let local = now.with_timezone(&self.timezone);
        if !self.hours.contains(&local.hour()) {
            return Ok(());
        }
        let slot = local.format("%Y-%m-%dT%H").to_string();
        let path = root.join(STATE);
        let mut state = self.state(root)?;
        match state.cycle.as_ref() {
            Some(cycle) if cycle.slot > slot => return Ok(()),
            Some(cycle) if cycle.slot == slot => {
                if !matches!(cycle.outcome, Outcome::Running | Outcome::Foreground) {
                    return Ok(());
                }
            }
            _ => {
                state.cycle = Some(Cycle {
                    slot,
                    completed: 0,
                    outcome: Outcome::Running,
                });
                rebuild::write_json(&path, &state)?;
            }
        }

        let advanced = state.advance(root, &path, self.include_tools, &mut call);
        let cycle = state.cycle.as_mut().ok_or("missing reflection cycle")?;
        let outcome = match advanced {
            Ok(true) => {
                cycle.completed += 1;
                if cycle.completed == MAX_BATCHES {
                    Outcome::Limit
                } else {
                    Outcome::Running
                }
            }
            Ok(false) => Outcome::Drained,
            Err(error) if foreground(&error) => Outcome::Foreground,
            Err(_) => Outcome::Held,
        };
        if outcome != cycle.outcome || matches!(outcome, Outcome::Running) {
            cycle.outcome = outcome;
            rebuild::write_json(&path, &state)?;
        }
        Ok(())
    }
}

impl State {
    fn advance(
        &mut self,
        root: &Path,
        path: &Path,
        include_tools: bool,
        call: &mut impl FnMut(&str, Value) -> Result<Value>,
    ) -> Result<bool> {
        if self.pending.is_none() {
            let page = call(
                "maintenance.history.page",
                json!({
                    "scope": self.stream.scope, "purpose": "reflect", "after": self.cursor
                }),
            )?;
            let Some(event) = first_source(&page, &self.stream.entry, self.cursor)? else {
                return Ok(false);
            };
            self.pending = Some(if include_tools {
                Pending::WithTools {
                    event,
                    tools: self.stream.tool_receipts(event, call)?,
                }
            } else {
                Pending::Event(event)
            });
            rebuild::write_json(path, self)?;
        }
        let pending = self.pending.as_ref().ok_or("missing scheduled sources")?;
        let event = pending.event();
        let batch = format!("scheduled-{:020}", self.serial);
        let job = json!({
            "action": "reflection.run", "batch": batch,
            "plan": {"scope": self.stream.scope, "route": self.stream.route,
                     "events": [event], "tools": pending.tools()}
        });
        let result = reflection::run(root, &batch, job, call)?;
        if !matches!(result["phase"].as_str(), Some("applied" | "erased")) {
            return Err("original scheduled reflection is unsettled".into());
        }
        self.settle(event)?;
        Ok(true)
    }

    fn settle(&mut self, event: u64) -> Result<()> {
        self.serial = self.serial.checked_add(1).ok_or("reflection batch limit")?;
        self.cursor = event;
        self.pending = None;
        Ok(())
    }
}

impl Stream {
    fn tool_receipts(
        &self,
        event: u64,
        call: &mut impl FnMut(&str, Value) -> Result<Value>,
    ) -> Result<Vec<ToolSelection>> {
        let mut selected = Vec::new();
        let mut after = 0;
        loop {
            let page = call(
                "maintenance.tool.page",
                json!({"scope": self.scope, "purpose": "reflect", "event": event, "after": after}),
            )?;
            let items = page["items"]
                .as_array()
                .ok_or("invalid scheduled tool page")?;
            for item in items {
                let receipt = item["receipt"]
                    .as_u64()
                    .filter(|id| *id > after)
                    .ok_or("unordered scheduled tool page")?;
                if item["entry"] != self.entry || selected.len() == MAX_TOOLS {
                    return Err("scheduled tool receipt outside entry or batch limit".into());
                }
                let tool = ToolSelection::from_page(item)?;
                if !tool.sources().contains(&event) {
                    return Err("scheduled tool receipt missing its trigger source".into());
                }
                selected.push(tool);
                after = receipt;
            }
            if page["next"] != after {
                return Err("tool cursor does not match its page".into());
            }
            if items.is_empty() {
                return Ok(selected);
            }
        }
    }
}

fn bounded(value: &str, limit: usize) -> bool {
    !value.trim().is_empty() && value.len() <= limit
}

fn foreground(error: &str) -> bool {
    serde_json::from_str::<Value>(error).is_ok_and(|value| {
        value["code"] == -32003 && value["message"] == "reflection_deferred_for_foreground"
    })
}

fn first_source(page: &Value, entry: &str, cursor: u64) -> Result<Option<u64>> {
    let items = page["items"]
        .as_array()
        .ok_or("invalid reflection history page")?;
    let next = page["next_event"]
        .as_u64()
        .ok_or("missing original history cursor")?;
    let mut last = cursor;
    let mut first = None;
    for item in items {
        let event = item["event"]
            .as_u64()
            .filter(|event| *event > last && i64::try_from(*event).is_ok())
            .ok_or("unordered reflection history page")?;
        if item["entry"] != entry || item["offset"] != 0 {
            return Err("reflection history outside the original entry".into());
        }
        first.get_or_insert(event);
        last = event;
    }
    if last != next {
        return Err("reflection history cursor does not match its page".into());
    }
    Ok(first)
}

pub fn erase(root: &Path, sources: &Value) -> Result<()> {
    let path = root.join(STATE);
    rebuild::remove(&path.with_extension("json.tmp"))?;
    rebuild::sync_dir(root).map_err(|error| error.to_string())?;
    let Some(mut state) = rebuild::read_json::<State>(&path)? else {
        return Ok(());
    };
    let erased: BTreeSet<u64> =
        serde_json::from_value(sources.clone()).map_err(|e| e.to_string())?;
    if let Some(pending) = state.pending.as_ref().filter(|pending| {
        erased.contains(&pending.event())
            || pending
                .tools()
                .iter()
                .flat_map(ToolSelection::sources)
                .any(|id| erased.contains(id))
    }) {
        state.settle(pending.event())?;
        rebuild::write_json(&path, &state)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_the_whole_page_before_selecting_its_first_event() {
        let mut page = json!({"items":[
            {"event":42,"entry":"original","offset":0},
            {"event":48,"entry":"original","offset":0}
        ],"next_event":48});
        assert_eq!(first_source(&page, "original", 40).unwrap(), Some(42));
        assert!(first_source(&page, "original", 42).is_err());
        page["items"][1]["entry"] = json!("other");
        assert!(first_source(&page, "original", 40).is_err());
        page["items"][1]["entry"] = json!("original");
        page["next_event"] = json!(49);
        assert!(first_source(&page, "original", 40).is_err());
        assert_eq!(
            first_source(&json!({"items":[],"next_event":40}), "original", 40).unwrap(),
            None
        );
    }

    #[test]
    fn tool_pages_freeze_complete_receipts_for_the_original_event() {
        let stream: Stream = serde_json::from_value(json!({
            "scope":"own","route":"review","entry":"original","after":40
        }))
        .unwrap();
        let original = json!({
            "execution":"work","receipt":7,"entry":"original","source_ids":[42,44],
            "source_count":2,"sources_complete":true,"complete":true,"version":"a".repeat(64)
        });
        let selected = stream
            .tool_receipts(42, &mut |method, args| {
                assert_eq!(method, "maintenance.tool.page");
                assert_eq!(args["event"], 42);
                Ok(if args["after"] == 0 {
                    json!({"items":[original],"next":7})
                } else {
                    assert_eq!(args["after"], 7);
                    json!({"items":[],"next":7})
                })
            })
            .unwrap();
        assert_eq!(selected[0].sources(), &[42, 44]);
        let mut wrong_entry = original.clone();
        wrong_entry["entry"] = "other".into();
        let mut incomplete = original;
        incomplete["sources_complete"] = false.into();
        for rejected in [wrong_entry, incomplete] {
            assert!(
                stream
                    .tool_receipts(42, &mut |_, _| Ok(json!({"items":[rejected],"next":7})))
                    .is_err()
            );
        }
    }
}
