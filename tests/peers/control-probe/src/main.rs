mod rpc;

use serde_json::json;
use std::{
    io,
    sync::{Arc, atomic::{AtomicBool, Ordering}},
    thread,
};
use yuki_plugin_sdk::{host::Incoming, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let mut workers = Vec::new();
    let result: Result<(), String> = loop {
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
                    let _ = tx.send(result.map_err(|e| e.to_string()));
                }
            }
            Incoming::Call { method, id, params } if method == "tool.call" => {
                let (r, s) = (rpc.clone(), stop.clone());
                workers.push(thread::spawn(move || {
                    let status = r.call("tool.status", json!({"handle": params["handle"]}), &s);
                    let args = &params["arguments"];
                    let mut request = json!({
                        "handle": params["handle"],
                        "method": args["method"],
                        "args": args["args"],
                    });
                    if args.get("forged_actor").is_some() {
                        request["actor"] = args["forged_actor"].clone();
                    }
                    let response = r.call("control.read", request.clone(), &s);
                    r.reply(id, json!({"ok": true, "data": {
                        "original_call": params, "status": status,
                        "request": request, "response": response,
                    }}));
                }));
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                // No private store exists in this diagnostic consumer. Do not
                // manufacture an owner cleanup proof or acknowledge work not done.
                let _ = rpc.send(&json!({"jsonrpc": "2.0", "id": id, "error": {
                    "code": -32602, "message": "diagnostic consumer has no registered private store",
                    "data": {"key": params["key"], "watermark": params["watermark"]}
                }}));
            }
            Incoming::Call { id, .. } => {
                let _ = rpc.send(&json!({"jsonrpc": "2.0", "id": id, "error": {
                    "code": -32601, "message": "control intake only"
                }}));
            }
            Incoming::Notification { .. } => (),
        }
    };
    stop.store(true, Ordering::Release);
    for worker in workers { let _ = worker.join(); }
    result?;
    Ok(())
}
