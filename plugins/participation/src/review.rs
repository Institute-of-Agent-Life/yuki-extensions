use super::{Host, Original, Result};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    fs::{File, OpenOptions},
    io::{self, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
};
use yuki_plugin_sdk::read_frame;

#[derive(Deserialize)]
struct PriorContext {
    anchor: Value,
    references: Vec<Value>,
}

pub(super) struct Engine {
    python: String,
    adapter: String,
    upstream: String,
    checkpoint: PathBuf,
    route: String,
    response_model: String,
    name: String,
    autonomous: bool,
    _lock: File,
}

impl Engine {
    pub(super) fn open(args: &[String]) -> Result<Self> {
        let [
            flag,
            python,
            adapter,
            upstream,
            checkpoint,
            route,
            response_model,
            name,
            owner @ ..,
        ] = args
        else {
            return Err("review requires --review <python> <bridge> <source-archive> <checkpoint> <route> <response-model> <name>".into());
        };
        if flag != "--review" || args.iter().any(String::is_empty) {
            return Err("invalid original review configuration".into());
        }
        let autonomous = match owner {
            [] => false,
            [option, mode] if option == "--owner" => match mode.as_str() {
                "semantic" => true,
                "legacy" | "off" => false,
                _ => return Err("invalid participation owner".into()),
            },
            _ => {
                return Err(
                    "optional participation owner requires --owner <legacy|semantic|off>".into(),
                );
            }
        };
        let checkpoint = PathBuf::from(checkpoint);
        let filename = checkpoint
            .file_name()
            .ok_or("missing private checkpoint filename")?;
        let checkpoint = checkpoint
            .parent()
            .ok_or("missing private checkpoint directory")?
            .canonicalize()?
            .join(filename);
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(checkpoint.with_extension("participation.lock"))?;
        lock.try_lock()?;
        Ok(Self {
            python: python.clone(),
            adapter: adapter.clone(),
            upstream: upstream.clone(),
            checkpoint,
            route: route.clone(),
            response_model: response_model.clone(),
            name: name.clone(),
            autonomous,
            _lock: lock,
        })
    }

    fn spawn(&self, persistent: bool) -> Result<Bridge> {
        let mut command = Command::new(&self.python);
        command
            .arg("-I")
            .arg("-B")
            .arg(&self.adapter)
            .arg(&self.upstream);
        if persistent {
            command.arg("--ticks");
        }
        let mut child = command
            .env_remove("YUKI_PLUGIN_BINDING")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        let input = child.stdin.take().ok_or("review bridge lacks input")?;
        let output = BufReader::new(child.stdout.take().ok_or("review bridge lacks output")?);
        Ok(Bridge {
            child,
            input,
            output,
        })
    }

    fn start(&self, job: &Value) -> Result<Bridge> {
        let mut bridge = self.spawn(false)?;
        bridge.send(job)?;
        Ok(bridge)
    }

    pub(super) fn autonomous(&self) -> bool {
        self.autonomous
    }

    pub(super) fn tick_reader(&self) -> Result<Bridge> {
        self.spawn(true)
    }

    pub(super) fn tick_checkpoint(&self) -> &Path {
        &self.checkpoint
    }

    pub(super) fn erase(&self, sources: &Value) -> Result<()> {
        let mut bridge =
            self.start(&json!({"action":"erase","checkpoint":self.checkpoint,"sources":sources}))?;
        bridge.require_done()
    }

    pub(super) fn pending(&self, entry: &str) -> Result<Vec<i64>> {
        if !self.checkpoint.is_file() {
            return Ok(Vec::new());
        }
        let mut bridge =
            self.start(&json!({"action":"pending","checkpoint":self.checkpoint,"entry":entry}))?;
        let mut pending = bridge.receive()?;
        if pending["type"] != "pending" {
            return Err("missing original pending reviews".into());
        }
        let events = serde_json::from_value(pending["events"].take())?;
        bridge.finish()?;
        Ok(events)
    }

    fn prior_context(&self, focus: &Value, receiver: &str) -> Result<Option<PriorContext>> {
        if !self.checkpoint.is_file() {
            return Ok(None);
        }
        let mut bridge = self.start(&json!({"action":"context","checkpoint":self.checkpoint,
            "focus":focus,"receiver":receiver}))?;
        let mut report = bridge.receive()?;
        if report["type"] != "context" {
            return Err("missing original participation context".into());
        }
        let context = serde_json::from_value(report["context"].take())?;
        bridge.finish()?;
        Ok(context)
    }
}

pub(super) struct Bridge {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}

impl Bridge {
    pub(super) fn send(&mut self, frame: &Value) -> Result<()> {
        writeln!(self.input, "{frame}")?;
        self.input.flush()?;
        Ok(())
    }

    pub(super) fn receive(&mut self) -> Result<Value> {
        let message = read_frame(&mut self.output)?.ok_or("review bridge ended before receipt")?;
        Ok(serde_json::from_slice(&message)?)
    }

    fn require_done(&mut self) -> Result<()> {
        if self.receive()?["type"] != "done" {
            return Err("review bridge did not settle".into());
        }
        self.finish()
    }

    fn finish(&mut self) -> Result<()> {
        if self.child.wait()?.success() {
            Ok(())
        } else {
            Err("review bridge exited unsuccessfully".into())
        }
    }
}

impl Drop for Bridge {
    fn drop(&mut self) {
        if self.child.try_wait().is_ok_and(|status| status.is_none()) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

impl<W: io::Write> Host<W> {
    pub(super) fn original_pages(&mut self, event: i64, mut first: Value) -> Result<Option<Value>> {
        let version = first["version"].clone();
        let origin = first["origin"].take();
        let delivery_origin = first["delivery_origin"].take();
        let end = first["size"].clone();
        let mut annotation = first["mentions"].take();
        let mut pieces = vec![];
        let mut page = first;
        loop {
            pieces.push(page["data"].take());
            if page["complete"] == true {
                break;
            }
            let Some(next) = self.request(
                "participation.source",
                json!({
                    "event":event,"include_self":true,"version":version,"cursor":page["next"]
                }),
            )?
            else {
                return Ok(None);
            };
            if next["next"].as_u64() <= page["next"].as_u64() {
                return Err("original source page did not advance".into());
            }
            page = next;
        }
        let mut mentions = vec![];
        while annotation.is_object() {
            let items = annotation["items"]
                .as_array_mut()
                .ok_or("missing original mentions")?;
            mentions.append(items);
            if annotation["complete"] == true {
                break;
            }
            let Some(next) = self.request(
                "participation.source",
                json!({
                    "event":event,"version":version,"cursor":end,"mention_cursor":annotation["next"]
                }),
            )?
            else {
                return Ok(None);
            };
            let next = next["mentions"].clone();
            if next["next"].as_u64() <= annotation["next"].as_u64() {
                return Err("original mention page did not advance".into());
            }
            annotation = next;
        }
        Ok(Some(
            json!({"event":event,"origin":origin,"delivery_origin":delivery_origin,
                "version":version,"mentions":mentions,"pages":pieces}),
        ))
    }

    fn review_response(&mut self, request: &Value) -> Result<Value> {
        let Some(receipt) = self.request("llm.complete", request.clone())? else {
            return Ok(json!({}));
        };
        if receipt["state"] != "response" || receipt["erased"] == true {
            return Ok(json!({}));
        }
        let mut offset = json!(0);
        let mut pages = vec![];
        let mut digest = Value::Null;
        loop {
            let Some(mut page) = self.request(
                "llm.result",
                json!({"request":receipt["request"],"offset":offset}),
            )?
            else {
                return Ok(json!({}));
            };
            if page["receipt"]["erased"] == true
                || page["sha256"].is_null()
                || !digest.is_null() && digest != page["sha256"]
            {
                return Ok(json!({}));
            }
            digest = page["sha256"].take();
            pages.push(page["bytes"].take());
            let next = page["next_offset"].take();
            if next.is_null() {
                return Ok(json!({"status":"response","pages":pages,"sha256":digest}));
            }
            if next.as_u64() <= offset.as_u64() {
                return Err("original Jev result page did not advance".into());
            }
            offset = next;
        }
    }

    fn admit_review(&mut self, event: i64, generation: u64, basis: &Value) -> Result<Value> {
        let mut params = basis.clone();
        params["event"] = json!(event);
        params["expected_generation"] = json!(generation);
        Ok(self
            .request("participation.promote", params)?
            .unwrap_or_else(|| json!({"status":"invalidated"})))
    }

    pub(super) fn review(&mut self, event: i64, engine: &Engine) -> Result<()> {
        let Some(first) = self.request("participation.source", json!({
            "event":event,"include_origin":true,"include_reply":true,"include_self":true,"mention_cursor":0
        }))? else { return Ok(()) };
        let origin: Original = serde_json::from_value(first["origin"].clone())?;
        if origin.entry != self.scope.entry
            || origin.observed_generation != Some(origin.current_generation)
        {
            return Ok(());
        }
        let reply = first["reply_to"].clone();
        let Some(focus) = self.original_pages(event, first)? else {
            return Ok(());
        };
        let native_reply = reply.is_object();
        let (reference, basis) = if native_reply {
            (reply.clone(), json!({"expected_reply":reply}))
        } else if let Some(context) = engine.prior_context(&focus, &self.scope.receiver)? {
            (
                context.anchor,
                json!({"expected_context":context.references}),
            )
        } else {
            return Ok(());
        };
        let anchor = reference["event"]
            .as_i64()
            .ok_or("missing original context event")?;
        let Some(first) = self.request("participation.source", json!({
            "event":anchor,"version":reference["version"],"include_origin":true,"include_self":true,
            "include_delivery_origin":true
        }))? else { return Ok(()) };
        let Some(earlier) = self.original_pages(anchor, first)? else {
            return Ok(());
        };
        let producer_event = earlier["delivery_origin"]["producer_event"].as_i64();
        let producer = if let Some(source) = producer_event {
            self.request(
                "participation.source",
                json!({"event":source,"include_origin":true}),
            )?
            .map(|page| json!({"event":source,"origin":page["origin"],"version":page["version"]}))
        } else {
            None
        };
        let mut bridge = engine.start(&json!({"action":"review","checkpoint":engine.checkpoint,
            "name":engine.name,"response_model":engine.response_model,"receiver":self.scope.receiver,
            "focus":focus,"anchor":earlier,"producer":producer,"native_reply":native_reply,
            "context":basis["expected_context"]}))?;
        let mut review = bridge.receive()?;
        if review["type"] == "feedback" {
            let source = review["event"]
                .as_i64()
                .filter(|source| *source == anchor || Some(*source) == producer_event)
                .ok_or("feedback source is outside the original reply")?;
            let feedback = self
                .request(
                    "participation.feedback",
                    json!({"event":source,"include_self_report":true}),
                )?
                .unwrap_or_else(|| json!({}));
            bridge.send(&feedback)?;
            review = bridge.receive()?;
        }
        if review["type"] == "fast" {
            let outcome = self.admit_review(event, origin.current_generation, &basis)?;
            bridge.send(&outcome)?;
            review = bridge.receive()?;
        }
        if review["type"] == "done" {
            return bridge.finish();
        }
        if review["type"] != "review" {
            return Err("unexpected original review request".into());
        }
        let response = self.review_response(&json!({"origin":{"event":event},"sources":[anchor],
            "route":engine.route,"purpose":"review","call_id":"ordinary-jev-v1","jev":review["wire"]}))?;
        bridge.send(&response)?;
        let decision = bridge.receive()?;
        if decision["type"] == "done" {
            return bridge.finish();
        }
        if decision["type"] != "decision" {
            return Err("unexpected original review decision".into());
        }
        let mut outcome = json!({});
        if decision["invited"] == true {
            outcome = self.admit_review(event, origin.current_generation, &basis)?;
        }
        if !self.erasures.is_empty() {
            outcome = json!({"status":"invalidated"});
        }
        bridge.send(&outcome)?;
        bridge.require_done()
    }
}
