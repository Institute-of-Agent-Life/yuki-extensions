mod ingress;
mod media;
mod transport;

use serde_json::{Value, json};
use std::{
    env, fs,
    io::{self, Write},
    path::{Path, PathBuf},
    sync::mpsc::{self, Receiver, RecvTimeoutError},
    thread,
    time::{Duration, Instant},
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

fn initialize(input: &HostInput, out: &mut impl Write) -> Result<(Calls, String, bool), Error> {
    let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
    let namespace = binding.namespace.clone();
    let media_grant = binding.grants.iter().any(|g| g == "gateway.media");
    let offer = binding.offer();
    let mut peer = Peer::new(binding)?;
    emit(out, &peer.request(Id::Number(1), offer)?)?;
    loop {
        let raw = frame(input)?;
        match peer.receive(&raw)? {
            Received::Reply(reply) => emit(out, &reply)?,
            Received::Response { result: Ok(_), .. } => {
                let reply: Value = serde_json::from_slice(&raw)?;
                let init = &reply["result"];
                let media = media_grant
                    && init["method_revisions"].as_array().is_some_and(|ms| {
                        ms.iter()
                            .any(|m| m["name"] == "gateway.media" && m["revision"] == 1)
                    });
                return Ok((Calls::negotiated(init)?, namespace, media));
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => {}
        }
    }
}

fn request(
    base: &str,
    token: &str,
    method: &str,
    params: &Value,
) -> Result<transport::Request, Error> {
    transport::start(
        &format!("{base}/bot{token}/{method}"),
        Some(params),
        16 * 1024 * 1024,
    )
}

fn api(base: &str, token: &str, method: &str, params: &Value) -> Result<Value, Error> {
    result(request(base, token, method, params)?.finish()?)
}

fn result(raw: Vec<u8>) -> Result<Value, Error> {
    let response: Value = serde_json::from_slice(&raw)?;
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

struct Gateway<'a> {
    namespace: &'a str,
    bot: i64,
    base: &'a str,
    token: &'a str,
    enabled: bool,
    media: media::Media,
}

impl Gateway<'_> {
    fn callback(&mut self, incoming: Incoming, out: &mut impl Write) -> Result<(), Error> {
        match incoming {
            Incoming::Notification { .. } => Ok(()),
            Incoming::Result { .. } => Err("unexpected gateway receipt".into()),
            Incoming::Call { id, method, params } => {
                let reply = if self.enabled && method == "gateway.media" {
                    match self
                        .media
                        .page(self.namespace, self.bot, self.base, self.token, &params)
                    {
                        Ok(page) => json!({"jsonrpc":"2.0","id":id,"result":page}),
                        Err(_) => {
                            json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"Telegram media unavailable"}})
                        }
                    }
                } else {
                    json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}})
                };
                emit(out, &reply)
            }
        }
    }
    fn tick(
        &mut self,
        input: &HostInput,
        calls: &mut Calls,
        out: &mut impl Write,
    ) -> Result<bool, Error> {
        self.media.expire();
        match input.recv_timeout(Duration::from_millis(25)) {
            Err(RecvTimeoutError::Disconnected) => Ok(false),
            Err(RecvTimeoutError::Timeout) => Ok(true),
            Ok(raw) => {
                self.callback(calls.receive(&raw?)?, out)?;
                Ok(true)
            }
        }
    }
}

fn main() -> Result<(), Error> {
    let (input, mut out) = (host_input(), io::stdout().lock());
    let (mut calls, namespace, enabled) = initialize(&input, &mut out)?;
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
    let mut gateway = Gateway {
        namespace: &namespace,
        bot,
        base: &base,
        token: &token,
        enabled,
        media: media::Media::default(),
    };
    loop {
        let mut params = json!({"timeout":30,"allowed_updates":["message","edited_message"]});
        if let Some(value) = offset {
            params["offset"] = value.into();
        }
        if !gateway.tick(&input, &mut calls, &mut out)? {
            return Ok(());
        }
        let mut poll = request(&base, &token, "getUpdates", &params)?;
        while !poll.ready()? {
            if !gateway.tick(&input, &mut calls, &mut out)? {
                return Ok(());
            }
        }
        let batch = match poll.finish().and_then(result) {
            Ok(v) => v,
            Err(_) => {
                let until = Instant::now() + Duration::from_secs(1);
                while Instant::now() < until {
                    if !gateway.tick(&input, &mut calls, &mut out)? {
                        return Ok(());
                    }
                }
                continue;
            }
        };
        for update in batch.as_array().ok_or("invalid Telegram batch")? {
            let id = update["update_id"].as_i64().ok_or("invalid update_id")?;
            if offset.is_some_and(|next| id < next) {
                continue;
            }
            let mut envelope = ingress::normalize(update, bot, username)?;
            if enabled {
                envelope["media_identity"] = json!({"application":bot.to_string()});
            }
            let request_id = Id::Number(id);
            let request = calls.request(request_id.clone(), "gateway.inbound", envelope)?;
            emit(&mut out, &request)?;
            loop {
                let raw = match input.recv_timeout(Duration::from_secs(1)) {
                    Ok(raw) => raw?,
                    Err(RecvTimeoutError::Timeout) => {
                        gateway.media.expire();
                        continue;
                    }
                    Err(RecvTimeoutError::Disconnected) => return Ok(()),
                };
                match calls.receive(&raw)? {
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
                    other => gateway.callback(other, &mut out)?,
                }
            }
            let next = id.checked_add(1).ok_or("offset overflow")?;
            commit_cursor(&dir, &cursor, next)?;
            offset = Some(next);
        }
    }
}
