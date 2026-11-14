mod query;
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
    let stop = Arc::new(AtomicBool::new(false));
    let mut workers = Vec::new();
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
            Incoming::Call { method, id, params }
                if method == "tool.call" || method == "command.invoke" =>
            {
                let (rpc, stop) = (rpc.clone(), stop.clone());
                // Reap completed requests so a long-running plugin does not
                // retain JoinHandles or result values from earlier queries.
                let mut running = Vec::new();
                for worker in workers.drain(..) {
                    let worker: thread::JoinHandle<()> = worker;
                    if worker.is_finished() {
                        let _ = worker.join();
                    } else {
                        running.push(worker);
                    }
                }
                workers = running;
                if workers.len() >= 16 {
                    rpc.reply(
                        id,
                        json!({"ok":false,"error":"trace query concurrency limit reached"}),
                    );
                    continue;
                }
                workers.push(thread::spawn(move || {
                    let selection = if method == "tool.call" && params["name"] == "trace_query" {
                        query::parameters(&params["arguments"]).map(|args| ("trace.read", args))
                    } else if method == "command.invoke" && params["name"] == "/ai/trace/export" {
                        query::export_parameters(
                            params["arguments"]["text"].as_str().unwrap_or_default(),
                        )
                        .map(|args| ("trace.export", args))
                    } else {
                        Err("unknown trace invocation")
                    };
                    let result = selection.map_err(str::to_owned).and_then(|(action, args)| {
                        rpc.call(
                            "control.read",
                            json!({
                                "handle":params["handle"],"method":action,"args":args
                            }),
                            &stop,
                        )
                    });
                    let response = match result {
                        Ok(page) => json!({"ok":true,"data":page}),
                        Err(error) => json!({"ok":false,"error":error}),
                    };
                    rpc.reply(id, response);
                }));
            }
            Incoming::Call { id, .. } => {
                let _ = rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{
                    "code":-32601,"message":"trace candidate supports on-demand queries only"
                }}));
            }
            Incoming::Notification { .. } => (),
        }
    };
    stop.store(true, Ordering::Release);
    for worker in workers {
        let _ = worker.join();
    }
    result?;
    Ok(())
}
