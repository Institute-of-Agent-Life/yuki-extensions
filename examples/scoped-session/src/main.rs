mod game;
mod rpc;

use serde_json::json;
use std::{
    io,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread::{self, JoinHandle},
};
use yuki_plugin_sdk::{Id, host::Incoming, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let cancel = Arc::new(AtomicBool::new(false));
    let mut worker: Option<JoinHandle<()>> = None;
    while let Some(raw) = read_frame(&mut input)? {
        let incoming = rpc.calls.lock().unwrap().receive(&raw)?;
        match incoming {
            Incoming::Result { id, result, .. } => {
                if let Some(sender) = rpc.pending.lock().unwrap().remove(&id) {
                    let _ = sender.send(result.map_err(|error| {
                        format!("host_error:{}", error["code"].as_i64().unwrap_or(-32000))
                    }));
                }
            }
            Incoming::Call { method, id, params } if method == "command.invoke" => {
                if worker.as_ref().is_some_and(|job| !job.is_finished()) {
                    rpc.reply(id, json!({"ok":false,"error":"game_busy"}));
                    continue;
                }
                if let Some(job) = worker.take() {
                    job.join().map_err(|_| "game worker failed")?;
                }
                let (rpc, cancel) = (rpc.clone(), cancel.clone());
                worker = Some(thread::spawn(move || {
                    let result = game::request(&params)
                        .and_then(|(method, args)| rpc.call(method, args, &cancel));
                    let response = match result {
                        Ok(data) => json!({"ok":true,"data":data}),
                        Err(error) => json!({"ok":false,"error":error}),
                    };
                    rpc.reply(id, response);
                }));
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                cancel.store(true, Ordering::Release);
                if let Some(job) = worker.take() {
                    job.join().map_err(|_| "game worker failed")?;
                }
                rpc.reply(id, json!({"key":params["key"],"watermark":params["watermark"],
                                     "proof":"lighthouse-request-worker-stopped-no-local-transcript"}));
                cancel.store(false, Ordering::Release);
            }
            Incoming::Call { id, .. } => {
                rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{
                    "code":-32601,"message":"method_not_found"
                }}))?;
            }
            Incoming::Notification { .. } => {}
        }
    }
    cancel.store(true, Ordering::Release);
    if let Some(job) = worker {
        job.join().map_err(|_| "game worker failed")?;
    }
    Ok(())
}
