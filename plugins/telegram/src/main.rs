mod ingress;

use serde_json::{Value, json};
use std::{
    env, fs,
    io::{self, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::mpsc::{self, Receiver, TryRecvError},
    thread,
    time::Duration,
};
use yuki_plugin_sdk::{
    Binding, Id, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};

type Error = Box<dyn std::error::Error>;

fn emit(out: &mut impl Write, msg: &Value) -> Result<(), Error> {
    writeln!(out, "{msg}")?;
    Ok(out.flush()?)
}

type HostInput = Receiver<io::Result<Vec<u8>>>;

fn host_input() -> HostInput {
    let (tx, rx) = mpsc::sync_channel(8);
    thread::spawn(move || {
        let mut input = io::stdin().lock();
        loop {
            match read_frame(&mut input) {
                Ok(Some(frame)) => {
                    if tx.send(Ok(frame)).is_err() {
                        break;
                    }
                }
                Ok(None) => break,
                Err(error) => {
                    let _ = tx.send(Err(error));
                    break;
                }
            }
        }
    });
    rx
}

fn frame(input: &HostInput) -> Result<Vec<u8>, Error> {
    Ok(input.recv()??)
}

fn initialize(input: &HostInput, out: &mut impl Write) -> Result<Calls, Error> {
    let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
    let offer = binding.offer();
    let mut peer = Peer::new(binding)?;
    emit(out, &peer.request(Id::Number(1), offer)?)?;
    loop {
        let raw = frame(input)?;
        match peer.receive(&raw)? {
            Received::Reply(reply) => emit(out, &reply)?,
            Received::Response { result: Ok(_), .. } => {
                let reply: Value = serde_json::from_slice(&raw)?;
                return Ok(Calls::negotiated(&reply["result"])?);
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => {}
        }
    }
}

// Keep the token in curl's stdin, outside its argv and diagnostics.
fn api(base: &str, token: &str, method: &str, params: &Value) -> Result<Value, Error> {
    let mut child = Command::new("curl")
        .args(["--disable", "--silent", "--max-time", "40", "--config", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let form = params
        .to_string()
        .replace('\\', "\\\\")
        .replace('"', "\\\"");
    {
        let mut stdin = child.stdin.take().ok_or("missing pipe")?;
        writeln!(
            stdin,
            "url = \"{base}/bot{token}/{method}\"\nheader = \"Content-Type: application/json\"\ndata = \"{form}\""
        )?;
    }
    let output = child.wait_with_output()?;
    if !output.status.success() {
        return Err("Telegram transport failed".into());
    }
    let response: Value = serde_json::from_slice(&output.stdout)?;
    if response["ok"] != true {
        return Err("Telegram API rejected call".into());
    }
    Ok(response["result"].clone())
}

fn commit_cursor(dir: &Path, cursor: &Path, offset: i64) -> Result<(), Error> {
    let tmp = cursor.with_extension("next");
    let mut f = fs::File::create(&tmp)?;
    writeln!(f, "{offset}")?;
    f.sync_all()?;
    drop(f);
    fs::rename(tmp, cursor)?;
    #[cfg(unix)]
    fs::File::open(dir)?.sync_all()?;
    #[cfg(not(unix))]
    let _ = dir;
    Ok(())
}

fn main() -> Result<(), Error> {
    let (input, mut out) = (host_input(), io::stdout().lock());
    let mut calls = initialize(&input, &mut out)?;
    let token = env::var("YUKI_TELEGRAM_TOKEN")?;
    let bot: i64 = env::var("YUKI_TELEGRAM_BOT_ID")?.parse()?;
    let (prefix, secret) = token.split_once(':').ok_or("invalid Telegram credential")?;
    if bot <= 0
        || prefix.parse::<i64>()? != bot
        || secret.is_empty()
        || !secret
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
    {
        return Err("credential identity mismatch".into());
    }
    let base = env::var("YUKI_TELEGRAM_API").unwrap_or_else(|_| "https://api.telegram.org".into());
    if base != "https://api.telegram.org"
        && !base
            .strip_prefix("http://127.0.0.1:")
            .is_some_and(|p| p.parse::<u16>().is_ok())
    {
        return Err("invalid Telegram endpoint".into());
    }
    let me = api(&base, &token, "getMe", &json!({}))?;
    if me["id"].as_i64() != Some(bot) || me["is_bot"] != true {
        return Err("unexpected Telegram bot".into());
    }
    let username = me["username"].as_str().ok_or("missing bot username")?;
    let dir = PathBuf::from(env::var_os("YUKI_TELEGRAM_STATE").ok_or("missing state directory")?);
    fs::create_dir_all(&dir)?;
    let lock = fs::File::options()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(dir.join(format!("{bot}.lock")))?;
    lock.try_lock()?;
    let cursor = dir.join(format!("{bot}.offset"));
    let mut offset = match fs::read_to_string(&cursor) {
        Ok(text) => Some(text.trim().parse::<i64>()?),
        Err(e) if e.kind() == io::ErrorKind::NotFound => None,
        Err(e) => return Err(e.into()),
    };
    loop {
        match input.try_recv() {
            Err(TryRecvError::Disconnected) => return Ok(()),
            Err(TryRecvError::Empty) => {}
            Ok(raw) => {
                match calls.receive(&raw?)? {
                    Incoming::Notification { .. } => {}
                    Incoming::Call { id, .. } => emit(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":id,
                        "error":{"code":-32601,"message":"method_not_found"}}),
                    )?,
                    Incoming::Result { .. } => return Err("unexpected gateway receipt".into()),
                }
                continue;
            }
        }
        let mut params = json!({"timeout":30,"allowed_updates":["message","edited_message"]});
        if let Some(value) = offset {
            params["offset"] = value.into();
        }
        let batch = match api(&base, &token, "getUpdates", &params) {
            Ok(v) => v,
            Err(_) => {
                thread::sleep(Duration::from_secs(1));
                continue;
            }
        };
        for update in batch.as_array().ok_or("invalid Telegram batch")? {
            let id = update["update_id"].as_i64().ok_or("invalid update_id")?;
            if offset.is_some_and(|next| id < next) {
                continue;
            }
            let envelope = ingress::normalize(update, bot, username)?;
            let request_id = Id::Number(id);
            let request = calls.request(request_id.clone(), "gateway.inbound", envelope)?;
            emit(&mut out, &request)?;
            loop {
                match calls.receive(&frame(&input)?)? {
                    Incoming::Result {
                        id: returned,
                        result: Ok(value),
                        ..
                    } if returned == request_id => {
                        if (!value["event"].as_u64().is_some_and(|event| event > 0)
                            && value["erased"] != true)
                            || !value["accepted"].is_boolean()
                        {
                            return Err("missing durable gateway receipt".into());
                        }
                        break;
                    }
                    Incoming::Result { .. } => return Err("gateway admission failed".into()),
                    Incoming::Notification { .. } => continue,
                    Incoming::Call { id, .. } => emit(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":id,"error":{
                        "code":-32601,"message":"method_not_found"}}),
                    )?,
                }
            }
            let next = id.checked_add(1).ok_or("offset overflow")?;
            commit_cursor(&dir, &cursor, next)?;
            offset = Some(next);
        }
    }
}
