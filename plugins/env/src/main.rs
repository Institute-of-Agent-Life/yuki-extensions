mod manager;

use serde_json::{Value, json};
use std::{
    env,
    io::{self, BufRead, Write},
};
use yuki_plugin_sdk::{
    Binding, Id, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};

type Error = Box<dyn std::error::Error>;
fn send(out: &mut impl Write, frame: &Value) -> Result<(), Error> {
    writeln!(out, "{frame}")?;
    Ok(out.flush()?)
}

fn handshake(input: &mut impl BufRead, out: &mut impl Write) -> Result<Calls, Error> {
    let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
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

struct StatusCall {
    id: Id,
    handle: String,
    operation: String,
    result: Option<Value>,
}
// Keep the host stream available for independent calls and opposite-direction replies.
fn main() -> Result<(), Error> {
    let (mut input, mut out) = (io::stdin().lock(), io::stdout().lock());
    let mut calls = handshake(&mut input, &mut out)?;
    let mut pending = std::collections::HashMap::<Id, StatusCall>::new();
    let mut sequence = 0_i64;
    while let Some(raw) = read_frame(&mut input)? {
        match calls.receive(&raw)? {
            Incoming::Call { method, id, params } => {
                if method != "tool.call" || params["name"] != "environment_status" {
                    send(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}),
                    )?;
                    continue;
                }
                if !params["arguments"]
                    .as_object()
                    .is_some_and(|args| args.is_empty())
                {
                    send(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":id,"result":{"ok":false,"error":"invalid_arguments"}}),
                    )?;
                    continue;
                }
                let operation = params["operation"]
                    .as_str()
                    .ok_or("missing original operation")?
                    .to_owned();
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
                    StatusCall {
                        id,
                        handle,
                        operation,
                        result: None,
                    },
                );
            }
            Incoming::Result { id, method, result } => {
                if method != "tool.status" {
                    return Err("unexpected result".into());
                }
                let mut call = pending.remove(&id).ok_or("unknown status")?;
                let active =
                    result.is_ok_and(|s| s["state"] == "dispatched" && s["handle"] == call.handle);
                if !active {
                    send(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":call.id,"result":{"ok":false,"error":"scope_unavailable"}}),
                    )?;
                } else if let Some(result) = call.result {
                    send(
                        &mut out,
                        &json!({"jsonrpc":"2.0","id":call.id,"result":result}),
                    )?;
                } else {
                    call.result = Some(match manager::status(&call.operation) {
                        Ok(data) => json!({"ok":true,"data":data}),
                        Err(error) => json!({"ok":false,"error":error}),
                    });
                    sequence = sequence.checked_add(1).ok_or("id overflow")?;
                    let check = Id::Number(sequence);
                    send(
                        &mut out,
                        &calls.request(
                            check.clone(),
                            "tool.status",
                            json!({"handle":call.handle}),
                        )?,
                    )?;
                    pending.insert(check, call);
                }
            }
            Incoming::Notification { .. } => {}
        }
    }
    Ok(())
}
