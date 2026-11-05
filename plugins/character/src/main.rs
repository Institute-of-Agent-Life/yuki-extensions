mod profile;
mod rpc;

use serde_json::json;
use std::{io, sync::{Arc, atomic::{AtomicBool, Ordering}}, thread};
use yuki_plugin_sdk::{host::Incoming, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let mut workers: Vec<thread::JoinHandle<()>> = Vec::new();
    let result: Result<(), String> = loop {
        let raw = match read_frame(&mut input) {
            Ok(Some(raw)) => raw,
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
                let mut running = Vec::new();
                for worker in workers.drain(..) {
                    if worker.is_finished() { let _ = worker.join(); }
                    else { running.push(worker); }
                }
                workers = running;
                if workers.len() >= 16 {
                    rpc.reply(id, json!({"ok":false,"error":"character request concurrency limit reached"}));
                    continue;
                }
                let (rpc, stop) = (rpc.clone(), stop.clone());
                workers.push(thread::spawn(move || {
                    let result = if params["name"] != "character_manage" {
                        Err("unknown character tool".to_owned())
                    } else {
                        profile::request(&params["arguments"], &params["handle"]).map_err(str::to_owned)
                            .and_then(|(method, args)| rpc.call(method, args, &stop))
                    };
                    let result = match result {
                        Ok(value) => json!({"ok":true,"data":value}),
                        Err(error) => json!({"ok":false,"error":error}),
                    };
                    rpc.reply(id, result);
                }));
            }
            Incoming::Call { id, .. } => {
                let _ = rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{
                    "code":-32601,"message":"shared role and SOUL candidate only"
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
