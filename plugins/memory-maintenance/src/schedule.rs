use crate::{rebuild, reflection};
use chrono::{DateTime, Timelike, Utc};
use chrono_tz::Tz;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path};

type Result<T> = std::result::Result<T, String>;
const MAX_BATCHES: u32 = 32;
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
}

#[derive(Deserialize, Serialize)]
struct State {
    stream: Stream,
    timezone: Tz,
    cursor: u64,
    serial: u64,
    pending: Option<u64>,
    cycle: Option<Cycle>,
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

        let advanced = state.advance(root, &path, &mut call);
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
        call: &mut impl FnMut(&str, Value) -> Result<Value>,
    ) -> Result<bool> {
        let event = match self.pending {
            Some(event) => event,
            None => {
                let page = call(
                    "maintenance.history.page",
                    json!({
                        "scope": self.stream.scope, "purpose": "reflect", "after": self.cursor
                    }),
                )?;
                let Some(event) = first_source(&page, &self.stream.entry, self.cursor)? else {
                    return Ok(false);
                };
                self.pending = Some(event);
                rebuild::write_json(path, self)?;
                event
            }
        };
        let batch = format!("scheduled-{:020}", self.serial);
        let job = json!({
            "action": "reflection.run", "batch": batch,
            "plan": {"scope": self.stream.scope, "route": self.stream.route, "events": [event]}
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
    let Some(mut state) = rebuild::read_json::<State>(&path)? else {
        return Ok(());
    };
    let erased: BTreeSet<u64> =
        serde_json::from_value(sources.clone()).map_err(|e| e.to_string())?;
    if let Some(event) = state.pending.filter(|event| erased.contains(event)) {
        state.settle(event)?;
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
}
