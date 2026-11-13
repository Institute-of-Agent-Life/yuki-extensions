mod fetch;
mod legacy;
mod policy;

use serde_json::{Value, json};
use std::{
    env,
    io::{self, BufRead, Write},
};
use yuki_plugin_sdk::{
    Binding, Id, MAX_FRAME_BYTES, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};

type Error = Box<dyn std::error::Error>;
fn send(out: &mut impl Write, frame: &Value) -> Result<(), Error> {
    writeln!(out, "{frame}")?;
    Ok(out.flush()?)
}

fn send_result(out: &mut impl Write, id: Id, result: Value) -> Result<(), Error> {
    let frame = serde_json::to_vec(&json!({"jsonrpc":"2.0","id":id,"result":result}))?;
    if frame.len() > MAX_FRAME_BYTES {
        return send(
            out,
            &json!({"jsonrpc":"2.0","id":id,"result":{"ok":false,"error":"result_too_large"}}),
        );
    }
    out.write_all(&frame)?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(())
}

fn handshake(
    input: &mut impl BufRead,
    out: &mut impl Write,
    binding: Binding,
) -> Result<Calls, Error> {
    let offer = binding.offer();
    let mut peer = Peer::new(binding)?;
    send(out, &peer.request(Id::Number(1), offer)?)?;
    while let Some(raw) = read_frame(input)? {
        match peer.receive(&raw)? {
            Received::Reply(reply) => send(out, &reply)?,
            Received::Response { result: Ok(_), .. } => {
                let msg: Value = serde_json::from_slice(&raw)?;
                return Ok(Calls::negotiated(&msg["result"])?);
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => {}
        }
    }
    Err("host disconnected".into())
}

struct PageCall {
    id: Id,
    handle: String,
    request: PageRequest,
    result: Option<Value>,
}

enum PageRequest {
    Fetch(String),
    Legacy(legacy::Request),
}

impl PageRequest {
    fn read(&self) -> Value {
        match self {
            Self::Legacy(request) => request.read(),
            Self::Fetch(url) => {
                let data = fetch::read(url);
                let state = data["state"].as_str().unwrap_or("invalid_result");
                if matches!(state, "read" | "partial" | "not_modified") {
                    json!({"ok":true,"data":data})
                } else {
                    json!({"ok":false,"error":state,"data":data})
                }
            }
        }
    }
}

fn main() -> Result<(), Error> {
    let (mut input, mut out) = (io::stdin().lock(), io::stdout().lock());
    let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
    let names: Vec<_> = binding
        .declarations
        .iter()
        .filter(|d| d.kind == "tool")
        .map(|d| d.name.as_str())
        .collect();
    let legacy_enabled = names.contains(&"read_webpage");
    let fetch_enabled = names.contains(&"web_fetch");
    let mut calls = handshake(&mut input, &mut out, binding)?;
    let mut pending = std::collections::HashMap::<Id, PageCall>::new();
    let mut sequence = 0_i64;
    while let Some(raw) = read_frame(&mut input)? {
        match calls.receive(&raw)? {
            Incoming::Call { method, id, params } => {
                let arguments = &params["arguments"];
                let request = match (method.as_str(), params["name"].as_str()) {
                    ("tool.call", Some("web_fetch")) if fetch_enabled => arguments["url"]
                        .as_str()
                        .map(|url| PageRequest::Fetch(url.into()))
                        .ok_or("invalid_url"),
                    ("tool.call", Some("read_webpage")) if legacy_enabled => {
                        legacy::Request::parse(arguments).map(PageRequest::Legacy)
                    }
                    _ => {
                        send(
                            &mut out,
                            &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}),
                        )?;
                        continue;
                    }
                };
                let request = match request {
                    Ok(request) => request,
                    Err(error) => {
                        send(
                            &mut out,
                            &json!({"jsonrpc":"2.0","id":id,"result":{"ok":false,"error":error}}),
                        )?;
                        continue;
                    }
                };
                let handle = params["handle"]
                    .as_str()
                    .ok_or("missing bound handle")?
                    .to_owned();
                sequence = sequence.checked_add(1).ok_or("id overflow")?;
                let check = Id::Number(sequence);
                send(
                    &mut out,
                    &calls.request(check.clone(), "tool.status", json!({"handle":handle}))?,
                )?;
                pending.insert(
                    check,
                    PageCall {
                        id,
                        handle,
                        request,
                        result: None,
                    },
                );
            }
            Incoming::Result { id, method, result } => {
                if method != "tool.status" {
                    return Err("unexpected result".into());
                }
                let mut page = pending.remove(&id).ok_or("unknown status")?;
                let active =
                    result.is_ok_and(|s| s["state"] == "dispatched" && s["handle"] == page.handle);
                if !active {
                    send(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":page.id,"result":{"ok":false,"error":"scope_unavailable"}}),
                    )?;
                } else if let Some(result) = page.result {
                    send_result(&mut out, page.id, result)?;
                } else {
                    page.result = Some(page.request.read());
                    sequence = sequence.checked_add(1).ok_or("id overflow")?;
                    let check = Id::Number(sequence);
                    send(
                        &mut out,
                        &calls.request(
                            check.clone(),
                            "tool.status",
                            json!({"handle":page.handle}),
                        )?,
                    )?;
                    pending.insert(check, page);
                }
            }
            Incoming::Notification { .. } => {}
        }
    }
    Ok(())
}
