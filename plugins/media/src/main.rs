mod inspect;
mod rpc;
use serde_json::json;
use std::{
    io,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
};
use yuki_plugin_sdk::{host::Incoming, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let mut tasks: Vec<(Arc<AtomicBool>, thread::JoinHandle<bool>)> = vec![];
    let mut cleanup_ok = true;
    while let Some(raw) = read_frame(&mut input)? {
        let message = rpc.calls.lock().unwrap().receive(&raw)?;
        match message {
            Incoming::Result { id, result, .. } => {
                if let Some(tx) = rpc.pending.lock().unwrap().remove(&id) {
                    let _ = tx.send(result.map_err(|_| "scope unavailable".into()));
                }
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                for (cancel, _) in &tasks {
                    cancel.store(true, Ordering::Release);
                }
                for (_, task) in tasks.drain(..) {
                    cleanup_ok &= task.join().unwrap_or(false);
                }
                if !cleanup_ok {
                    let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"temporary_cleanup_failed"}}));
                    continue;
                }
                rpc.reply(id,json!({"key":params["key"],"watermark":params["watermark"],"proof":"volatile-decoders-stopped-and-temporary-files-removed"}));
            }
            Incoming::Call { method, id, params } if method == "media.process" => {
                let mut index = 0;
                while index < tasks.len() {
                    if tasks[index].1.is_finished() {
                        let (_, task) = tasks.swap_remove(index);
                        cleanup_ok &= task.join().unwrap_or(false);
                    } else {
                        index += 1;
                    }
                }
                if tasks.len() >= 4 {
                    rpc.reply(id, json!({"ok":false,"error":"processor_busy"}));
                    continue;
                }
                let cancel = Arc::new(AtomicBool::new(false));
                let worker_cancel = cancel.clone();
                let worker_rpc = rpc.clone();
                let task = thread::spawn(move || {
                    let result = match inspect::process(&worker_rpc, &params, &worker_cancel) {
                        Ok(data) => json!({"ok":true,"data":data}),
                        Err(error) => json!({"ok":false,"error":error}),
                    };
                    let clean = result["error"] != "temporary_cleanup_failed";
                    worker_rpc.reply(id, result);
                    clean
                });
                tasks.push((cancel, task));
            }
            Incoming::Call { id, .. } => {
                let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}));
            }
            Incoming::Notification { .. } => (),
        }
    }
    for (cancel, _) in &tasks {
        cancel.store(true, Ordering::Release);
    }
    for (_, task) in tasks {
        let _ = task.join();
    }
    Ok(())
}
