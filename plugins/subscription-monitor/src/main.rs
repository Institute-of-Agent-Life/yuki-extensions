mod feed;
mod journal;
mod rpc;
use serde_json::{Value, json};
use std::{
    collections::HashSet,
    fs,
    io::{self, Read, Write},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use yuki_plugin_sdk::{host::Incoming, read_frame};
fn fetch(config: &Value, url: &str) -> Result<Value, String> {
    if !(url.starts_with("https://") || url.starts_with("http://127.0.0.1:"))
        || url.chars().any(char::is_control)
        || url.contains('@')
    {
        return Err("source endpoint requires HTTPS or explicit local service".into());
    }
    let mut child = Command::new("curl")
        .args([
            "--disable",
            "--silent",
            "--fail",
            "--globoff",
            "--proto",
            "=http,https",
            "--max-time",
            "10",
            "--max-filesize",
            "1048576",
            "--config",
            "-",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "curl unavailable")?;
    let result = (|| {
        let mut input = child.stdin.take().ok_or("curl pipe missing")?;
        writeln!(
            input,
            "url = \"{}\"",
            url.replace('\\', "\\\\").replace('"', "\\\"")
        )
        .map_err(|_| "curl input failed")?;
        if let Some(name) = config["token_env"].as_str() {
            let token = std::env::var(name).map_err(|_| "source credential unavailable")?;
            if token.chars().any(char::is_control) {
                return Err("invalid source credential".to_owned());
            }
            writeln!(
                input,
                "header = \"X-Auth-Token: {}\"",
                token.replace('\\', "\\\\").replace('"', "\\\"")
            )
            .map_err(|_| "curl credential input failed")?;
        }
        drop(input);
        let mut raw = vec![];
        child
            .stdout
            .take()
            .ok_or("curl output missing")?
            .take(1048577)
            .read_to_end(&mut raw)
            .map_err(|_| "source read failed")?;
        if raw.len() > 1048576 {
            return Err("source response too large".into());
        }
        if !child.wait().map_err(|_| "curl wait failed")?.success() {
            return Err("source HTTP observation failed".into());
        }
        serde_json::from_slice(&raw).map_err(|_| "invalid source JSON".into())
    })();
    let _ = child.kill();
    let _ = child.wait();
    result
}

fn observe(config: &Value, stop: &AtomicBool) -> Result<Value, String> {
    let url = feed::text(config, "url")?;
    if config["kind"] != "miniflux" {
        return fetch(config, url);
    }
    if url.contains('#') {
        return Err("Miniflux URL cannot contain a fragment".into());
    }
    let (path, query) = url.split_once('?').unwrap_or((url, ""));
    let mut filters = Vec::new();
    let mut limit = 100;
    let mut before = None;
    for field in query.split('&').filter(|field| !field.is_empty()) {
        let (name, value) = field.split_once('=').unwrap_or((field, ""));
        if name.is_empty()
            || !name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        {
            return Err("invalid Miniflux filter name".into());
        }
        match name {
            "offset" if value != "0" => return Err("Miniflux offset must be zero".into()),
            "order" | "direction" | "offset" => {}
            "limit" => {
                limit = value
                    .parse::<usize>()
                    .ok()
                    .filter(|n| *n > 0)
                    .ok_or("invalid Miniflux page size")?
                    .min(100);
            }
            "before_entry_id" => {
                before = Some(
                    value
                        .parse::<i64>()
                        .ok()
                        .filter(|n| *n > 0)
                        .ok_or("invalid Miniflux before_entry_id")?,
                );
            }
            _ => filters.push(field),
        }
    }
    let mut base = format!("{path}?order=id&direction=desc&limit={limit}");
    for filter in filters {
        base.push('&');
        base.push_str(filter);
    }
    let mut entries = Vec::new();
    let mut remaining = None;
    for _ in 0..20 {
        if stop.load(Ordering::Acquire) {
            return Err("observation interrupted".into());
        }
        let mut page = match before {
            Some(id) => fetch(config, &format!("{base}&before_entry_id={id}")),
            None => fetch(config, &base),
        }?;
        let count = page["total"].as_u64().ok_or("missing Miniflux total")?;
        if count > (20 * limit) as u64 {
            return Err("Miniflux collection exceeded the observation limit".into());
        }
        if remaining.is_some_and(|expected| expected != count) {
            return Err("Miniflux collection changed between pages".into());
        }
        let values = std::mem::take(
            page.get_mut("entries")
                .and_then(Value::as_array_mut)
                .ok_or("missing Miniflux entries")?,
        );
        if values.len() > limit || values.len() as u64 > count {
            return Err("invalid Miniflux page length".into());
        }
        for item in &values {
            before = Some(
                item["id"]
                    .as_i64()
                    .filter(|id| *id > 0 && before.is_none_or(|previous| *id < previous))
                    .ok_or("unstable Miniflux page order")?,
            );
        }
        let next = count - values.len() as u64;
        if next == 0 {
            entries.extend(values);
            let mut complete = json!({"total": entries.len()});
            complete["entries"] = Value::Array(entries);
            return Ok(complete);
        }
        if values.is_empty() {
            break;
        }
        entries.extend(values);
        remaining = Some(next);
    }
    Err("incomplete Miniflux collection; cursor unchanged".into())
}
fn worker(
    rpc: Arc<rpc::Rpc>,
    home: PathBuf,
    journal: Arc<Mutex<journal::Journal>>,
    stop: Arc<AtomicBool>,
) -> Result<(), String> {
    while !stop.load(Ordering::Acquire) {
        let raw = fs::read(home.join("subscriptions.json")).map_err(|e| e.to_string())?;
        if raw.len() > 1024 * 1024 {
            return Err("subscription configuration too large".into());
        }
        let config: Value = serde_json::from_slice(&raw).map_err(|_| "invalid configuration")?;
        let configs = config["subscriptions"]
            .as_array()
            .ok_or("missing subscriptions")?;
        let mut ids = std::collections::HashSet::new();
        for c in configs {
            if !ids.insert(feed::text(c, "id")?) {
                return Err("duplicate subscription ID".into());
            }
        }
        for c in configs {
            if c["enabled"] == false {
                continue;
            }
            let sid = feed::text(c, "id")?;
            let mut state = journal.lock().unwrap().state["subscriptions"][sid].clone();
            if state["pending"].as_array().is_none_or(|p| p.is_empty()) {
                let now = feed::timestamp(
                    SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .map_err(|_| "clock before epoch")?
                        .as_secs(),
                )?;
                match observe(c, &stop).and_then(|raw| feed::admit(c, &state, &raw, &now)) {
                    Ok(v) => state = v,
                    Err(e) => {
                        let mut j = journal.lock().unwrap();
                        let mut all = j.state.clone();
                        all["errors"][sid] = e.into();
                        j.commit(all)?;
                        continue;
                    }
                }
                let mut j = journal.lock().unwrap();
                let mut all = j.state.clone();
                all["subscriptions"][sid] = state.clone();
                all["errors"][sid] = Value::Null;
                j.commit(all)?;
            }
            for _ in 0..10 {
                if stop.load(Ordering::Acquire) {
                    break;
                }
                let Some(request) = state["pending"].as_array().and_then(|a| a.first()).cloned()
                else {
                    break;
                };
                let unresolved = !state["publishing"].is_null();
                state["publishing"] = request["event_key"].clone();
                {
                    let mut j = journal.lock().unwrap();
                    let mut all = j.state.clone();
                    all["subscriptions"][sid] = state.clone();
                    j.commit(all)?;
                }
                match rpc.call("notification.publish", request.clone(), &stop) {
                    Ok(receipt) => {
                        state["receipts"]
                            .as_array_mut()
                            .ok_or("invalid receipts")?
                            .push(json!({"request":request,"publication":receipt}));
                        state["pending"].as_array_mut().unwrap().remove(0);
                        state["publishing"] = Value::Null;
                        state["error"] = Value::Null;
                    }
                    Err(e) => {
                        if !unresolved && matches!(e, rpc::Failure::Rejected(_)) {
                            state["publishing"] = Value::Null;
                        }
                        state["error"] = e.to_string().into();
                        let mut j = journal.lock().unwrap();
                        let mut all = j.state.clone();
                        all["subscriptions"][sid] = state.clone();
                        j.commit(all)?;
                        break;
                    }
                }
                let mut j = journal.lock().unwrap();
                let mut all = j.state.clone();
                all["subscriptions"][sid] = state.clone();
                j.commit(all)?;
            }
        }
        let interval = config["poll_seconds"].as_u64().unwrap_or(30).clamp(1, 3600);
        for _ in 0..interval * 10 {
            if stop.load(Ordering::Acquire) {
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let home = PathBuf::from(std::env::var("YUKI_SUBSCRIPTION_HOME")?).canonicalize()?;
    let journal = Arc::new(Mutex::new(journal::Journal::open(
        &home.join("state.jsonl"),
    )?));
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let (r, h, j, s) = (rpc.clone(), home.clone(), journal.clone(), stop.clone());
    let mut worker = (std::env::var("YUKI_PLUGIN_START_MODE").as_deref() != Ok("erasure_only"))
        .then(|| {
            thread::spawn(move || {
                let result = worker(r, h.clone(), j, s);
                if let Err(e) = &result {
                    let _ = fs::write(h.join("worker-error.txt"), e);
                }
                result
            })
        });
    let mut admin = vec![];
    let stream: Result<(), String> = loop {
        let raw = match read_frame(&mut input) {
            Ok(Some(v)) => v,
            Ok(None) => break Ok(()),
            Err(e) => break Err(e.to_string()),
        };
        let incoming = match rpc.calls.lock().unwrap().receive(&raw) {
            Ok(v) => v,
            Err(e) => break Err(e.to_string()),
        };
        match incoming {
            Incoming::Result { id, result, .. } => {
                if let Some(tx) = rpc.pending.lock().unwrap().remove(&id) {
                    let _ = tx.send(result);
                }
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                stop.store(true, Ordering::Release);
                let stopped = worker.take().is_none_or(|handle| handle.join().is_ok());
                let sources = serde_json::from_value::<HashSet<i64>>(params["sources"].clone());
                let erased = stopped
                    && sources.is_ok_and(|sources| {
                        !sources.is_empty() && journal.lock().unwrap().erase(&sources).is_ok()
                    });
                if erased {
                    rpc.reply(
                        id,
                        json!({"key":params["key"],"watermark":params["watermark"],
                        "proof":"matching subscription publications removed"}),
                    );
                } else {
                    let _ = rpc.send(&json!({"jsonrpc":"2.0","id":id,
                        "error":{"code":-32000,"message":"subscription_erasure_incomplete"}}));
                }
            }
            Incoming::Call { method, id, params }
                if method == "tool.call" && !stop.load(Ordering::Acquire) =>
            {
                let (r, s) = (rpc.clone(), stop.clone());
                admin.retain(|handle: &thread::JoinHandle<()>| !handle.is_finished());
                admin.push(thread::spawn(move || {
                    let args = &params["arguments"];
                    let action = args["action"].as_str().unwrap_or("");
                    let result = match action {
                        "grant_target" | "revoke_target" => {
                            let mut request = json!({"handle":params["handle"],
                                "key":format!("subscription:{}:{}", action, params["operation"].as_str().unwrap_or("")),
                                "target":args["target"]});
                            if action == "grant_target" && args["bot_user_id"].is_string() {
                                request["bot_user_id"] = args["bot_user_id"].clone();
                            }
                            r.call(&format!("notification.{action}"), request, &s)
                        }
                        "status" => r.call("notification.status", json!({}), &s),
                        _ => Err(rpc::Failure::Unknown("unknown subscription administrator action")),
                    };
                    r.reply(id, match result {
                        Ok(v) => json!({"ok":true,"data":v}),
                        Err(e) => json!({"ok":false,"error":e.to_string()}),
                    });
                }));
            }
            Incoming::Call { id, .. } => {
                let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"unsupported subscription callback"}}));
            }
            Incoming::Notification { .. } => (),
        }
    };
    stop.store(true, Ordering::Release);
    let result = worker.map_or(Ok(()), |handle| {
        handle.join().map_err(|_| "subscription worker panicked")?
    });
    for a in admin {
        let _ = a.join();
    }
    stream?;
    result?;
    Ok(())
}
