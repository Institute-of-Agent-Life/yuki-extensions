use super::{
    Host, Result,
    review::{Bridge, Engine},
};
use serde_json::{Value, json};
use std::io::Write;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const TICK_INTERVAL: Duration = Duration::from_secs(2);
const INSTRUCTION_START: &str = concat!(
    "自主工作唤醒：先按需核对已有 Work、待办及相关资料，静默推进未完成事项、",
    "重要的人已表达的关切或事件进展，也可整理工作区、研究或创作。",
);
const INSTRUCTION_END: &str = concat!(
    "沿原工作保存必要发现和下一步，可委派独立子任务；持续目标本轮暂无变化时，",
    "用 task_control wait 等后续信号或复查时间。没有需要继续的工作才安静结束。",
    "不要因醒来或群里安静主动开话题、打招呼、追问或找人聊天。已有任务需要反馈、约定提醒",
    "到期或重要变化确实需要对方知道或决定时，再用 send 简短说明。",
    "来源引用如下，详情可按需查询："
);

fn proposal_params(frame: &Value, entry: &str, generation: u64) -> Result<Value> {
    let key = frame["key"].as_str().ok_or("missing original SELF key")?;
    let mut params = json!({"entry":entry,"key":key,"expected_generation":generation});
    let (origin, references) = match frame["kind"].as_str() {
        Some("intrinsic") => (
            "这是你自己的工作唤醒，没有新的真人请求；不要把旧消息当成刚发生。",
            Vec::new(),
        ),
        Some("conversation") => {
            let sources: Vec<i64> = serde_json::from_value(frame["sources"].clone())?;
            let references = sources
                .iter()
                .map(|event| json!({"kind":"event","id":event.to_string()}))
                .collect();
            params["sources"] = json!(sources);
            params["source_guard"] = frame["source_guard"].clone();
            (
                "所附来源是本次工作的线索，不是某个用户的新请求。",
                references,
            )
        }
        _ => return Err("unknown original SELF proposal kind".into()),
    };
    params["text"] = json!(format!(
        "{INSTRUCTION_START}{origin}{INSTRUCTION_END}{}",
        json!(references)
    ));
    Ok(params)
}

pub(super) struct Timer<'a> {
    engine: &'a Engine,
    bridge: Option<Bridge>,
    next: Instant,
    generation: Option<u64>,
    cursor: i64,
    resumed: bool,
}

impl<'a> Timer<'a> {
    pub(super) fn new(engine: &'a Engine) -> Self {
        Self {
            engine,
            bridge: None,
            next: Instant::now(),
            generation: None,
            cursor: 0,
            resumed: true,
        }
    }

    pub(super) fn remaining(&self) -> Duration {
        self.next.saturating_duration_since(Instant::now())
    }

    pub(super) fn advance<W: Write>(&mut self, host: &mut Host<W>) -> Result<()> {
        let result = self.advance_scene(host);
        self.next = Instant::now() + TICK_INTERVAL;
        result
    }

    fn advance_scene<W: Write>(&mut self, host: &mut Host<W>) -> Result<()> {
        let entry = host.scope.entry.clone();
        let Some(page) = host.request(
            "participation.sources",
            json!({"entry":entry,"after":self.cursor,"include_generation":true}),
        )?
        else {
            self.resumed = true;
            return Ok(());
        };
        let generation = page["current_generation"]
            .as_u64()
            .filter(|value| *value > 0)
            .ok_or("missing original SELF generation")?;
        if page["entry"] != entry {
            return Err("SELF source page was from another entry".into());
        }
        let items = page["items"]
            .as_array()
            .ok_or("missing original source list")?;
        let next = page["next"]
            .as_i64()
            .ok_or("missing original source cursor")?;
        let mut sources = Vec::with_capacity(items.len());
        let mut last = self.cursor;
        for item in items {
            let event = item["event"]
                .as_i64()
                .filter(|event| *event > last)
                .ok_or("original SELF source cursor did not advance")?;
            last = event;
            let Some(first) = host.request(
                "participation.source",
                json!({"event":event,"version":item["version"],"include_origin":true,"mention_cursor":0}),
            )? else {
                self.resumed = true;
                return Ok(());
            };
            if first["origin"]["observed_generation"] != generation
                || first["origin"]["current_generation"] != generation
                || first["origin"]["entry"] != entry
            {
                self.resumed = true;
                return Ok(());
            }
            let Some(source) = host.original_pages(event, first)? else {
                self.resumed = true;
                return Ok(());
            };
            sources.push(source);
        }
        if next != last {
            return Err("SELF cursor differs from the source list".into());
        }
        if self.bridge.is_none() {
            self.bridge = Some(self.engine.tick_reader()?);
        }
        let bridge = self
            .bridge
            .as_mut()
            .ok_or("missing original SELF controller")?;
        let early = self.resumed || self.generation != Some(generation);
        let can_sample = items.len() < 8 && !early;
        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs_f64();
        bridge.send(&json!({
            "action":"tick","checkpoint":self.engine.tick_checkpoint(),
            "entry":entry,"receiver":host.scope.receiver,"generation":generation,"now":now,
            "resumed":early,"can_sample":can_sample,"sources":sources,"next":next
        }))?;
        loop {
            let frame = bridge.receive()?;
            match frame["type"].as_str() {
                Some("done") => {
                    let cursor = frame["cursor"]
                        .as_i64()
                        .filter(|cursor| *cursor >= next)
                        .ok_or("SELF controller cursor regressed")?;
                    self.cursor = cursor;
                    self.generation = Some(generation);
                    self.resumed = items.len() == 8;
                    return Ok(());
                }
                Some("feedback") => {
                    let key = frame["key"].as_str().ok_or("missing original SELF key")?;
                    let reply = host.request(
                        "participation.feedback",
                        json!({"key":key,"allow_missing_proposal":true,"include_delivery_time":true}),
                    )?;
                    bridge.send(&reply.unwrap_or(Value::Null))?;
                }
                Some("propose") if can_sample => {
                    let reply = if host.erasures.is_empty() {
                        host.request(
                            "participation.self_propose",
                            proposal_params(&frame, &entry, generation)?,
                        )?
                    } else {
                        None
                    };
                    bridge.send(&reply.unwrap_or(Value::Null))?;
                }
                _ => return Err("unexpected original SELF controller frame".into()),
            }
        }
    }
}
