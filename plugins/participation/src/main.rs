use serde::Deserialize;
use serde_json::{Value, json};
use std::{collections::VecDeque, env, io};
use yuki_plugin_sdk::{
    Binding, Id, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

struct Scope {
    entry: String,
    receiver: String,
}

#[derive(Deserialize)]
struct Original {
    entry: String,
    current_generation: u64,
    observed_generation: Option<u64>,
}

#[derive(Deserialize)]
struct MentionPage {
    items: Vec<Mention>,
    next: u64,
    complete: bool,
}

#[derive(Deserialize)]
struct Mention {
    kind: String,
    presence_id: Option<String>,
}

struct Host<R, W> {
    input: R,
    output: W,
    calls: Calls,
    scope: Scope,
    counter: i64,
    notices: VecDeque<i64>,
    erasures: Vec<(Id, Value)>,
    reading: Option<i64>,
}

impl<R: io::BufRead, W: io::Write> Host<R, W> {
    fn connect(mut input: R, mut output: W, scope: Scope) -> Result<Self> {
        let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
        let offer = binding.offer();
        let mut peer = Peer::new(binding)?;
        writeln!(output, "{}", peer.request(Id::Number(1), offer)?)?;
        output.flush()?;
        while let Some(raw) = read_frame(&mut input)? {
            match peer.receive(&raw)? {
                Received::Response { result: Ok(_), .. } => {
                    let frame: Value = serde_json::from_slice(&raw)?;
                    return Ok(Self {
                        input,
                        output,
                        calls: Calls::negotiated(&frame["result"])?,
                        scope,
                        counter: 1,
                        notices: VecDeque::new(),
                        erasures: Vec::new(),
                        reading: None,
                    });
                }
                Received::Response { result: Err(_), .. } => {
                    return Err("Host refused participation".into());
                }
                Received::Reply(frame) => {
                    writeln!(output, "{frame}")?;
                    output.flush()?;
                }
                Received::Notification => (),
            }
        }
        Err("Host ended participation handshake".into())
    }

    fn send(&mut self, frame: &Value) -> Result<()> {
        writeln!(self.output, "{frame}")?;
        self.output.flush()?;
        Ok(())
    }

    fn receive(&mut self) -> Result<Option<Incoming>> {
        read_frame(&mut self.input)?
            .map(|frame| self.calls.receive(&frame).map_err(Into::into))
            .transpose()
    }

    fn observe(&mut self, incoming: Incoming) -> Result<()> {
        match incoming {
            Incoming::Notification { method, params } if method == "observer.event" => {
                if params["kind"] == "message"
                    && params["entry"] == self.scope.entry
                    && let Some(event) = params["event"].as_i64()
                    && !self.notices.contains(&event)
                {
                    if self.notices.len() >= 256 {
                        return Err("participation observation queue exceeded 256 IDs".into());
                    }
                    self.notices.push_back(event);
                }
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                let sources: Vec<i64> = serde_json::from_value(params["sources"].clone())?;
                self.notices.retain(|event| !sources.contains(event));
                if self.reading.is_some_and(|event| sources.contains(&event)) {
                    self.reading = None;
                }
                self.erasures.push((id, params));
            }
            Incoming::Notification { .. } => (),
            _ => return Err("unexpected participation frame".into()),
        }
        Ok(())
    }

    fn acknowledge_erasure(&mut self) -> Result<()> {
        for (id, params) in std::mem::take(&mut self.erasures) {
            self.send(&json!({"jsonrpc":"2.0","id":id,"result":{
                "key":params["key"],"watermark":params["watermark"],
                "proof":"participation Rule has released affected volatile sources"
            }}))?;
        }
        Ok(())
    }

    fn request(&mut self, method: &str, params: Value) -> Result<Option<Value>> {
        self.counter += 1;
        let id = Id::Number(self.counter);
        let frame = self.calls.request(id.clone(), method, params)?;
        self.send(&frame)?;
        while let Some(frame) = self.receive()? {
            match frame {
                Incoming::Result {
                    id: response,
                    result,
                    ..
                } if response == id => {
                    return Ok(if self.reading.is_some() && self.erasures.is_empty() {
                        result.ok()
                    } else {
                        None
                    });
                }
                other => self.observe(other)?,
            }
        }
        Err("Host ended during participation request".into())
    }

    fn rule(&mut self, event: i64) -> Result<()> {
        let Some(page) = self.request(
            "participation.source",
            json!({
                "event":event,"include_origin":true,"mention_cursor":0
            }),
        )?
        else {
            return Ok(());
        };
        let origin: Original = serde_json::from_value(page["origin"].clone())?;
        if origin.entry != self.scope.entry
            || origin.observed_generation != Some(origin.current_generation)
        {
            return Ok(());
        }
        let version = page["version"]
            .as_str()
            .ok_or("missing original source version")?
            .to_owned();
        let end = page["size"]
            .as_u64()
            .ok_or("missing original source size")?;
        let mut mentions: MentionPage = serde_json::from_value(page["mentions"].clone())?;
        drop(page);
        let mut addressed = false;
        loop {
            for mention in mentions.items.iter().filter(|item| item.kind == "yuki") {
                if mention.presence_id.as_deref() != Some(self.scope.receiver.as_str()) {
                    return Ok(());
                }
                addressed = true;
            }
            if mentions.complete {
                break;
            }
            let offset = mentions.next;
            let Some(next) = self.request(
                "participation.source",
                json!({
                    "event":event,"version":version,"cursor":end,"mention_cursor":offset
                }),
            )?
            else {
                return Ok(());
            };
            mentions = serde_json::from_value(next["mentions"].clone())?;
            if mentions.next <= offset {
                return Err("original mention cursor did not advance".into());
            }
        }
        if addressed {
            self.request(
                "participation.promote",
                json!({
                    "event":event,"expected_generation":origin.current_generation
                }),
            )?;
        }
        Ok(())
    }

    fn run(&mut self) -> Result<()> {
        loop {
            self.acknowledge_erasure()?;
            if let Some(event) = self.notices.pop_front() {
                self.reading = Some(event);
                self.rule(event)?;
                if self.reading == Some(event) && !self.erasures.is_empty() {
                    self.notices.retain(|queued| *queued != event);
                    self.notices.push_front(event);
                }
                self.reading = None;
            } else if let Some(incoming) = self.receive()? {
                self.observe(incoming)?;
            } else {
                return Ok(());
            }
        }
    }
}

fn main() -> Result<()> {
    let args: Vec<_> = env::args().skip(1).collect();
    let [entry, receiver] = args.as_slice() else {
        return Err("usage: yuki-participation <entry> <receiving-stage>".into());
    };
    if entry.is_empty() || receiver.is_empty() {
        return Err("participation needs an original entry and receiving stage".into());
    }
    Host::connect(
        io::stdin().lock(),
        io::stdout().lock(),
        Scope {
            entry: entry.clone(),
            receiver: receiver.clone(),
        },
    )?
    .run()
}
