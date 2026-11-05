mod rpc;
use serde_json::{Value, json};
use std::{
    fs, io,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::Duration,
};
use yuki_plugin_sdk::{host::Incoming, read_frame};
fn probe(rpc: Arc<rpc::Rpc>, root: PathBuf, stop: Arc<AtomicBool>) -> Result<(), String> {
    let request = root.join("request.json");
    while !request.exists() {
        if stop.load(Ordering::Acquire) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(50));
    }
    let job: Value = serde_json::from_slice(&fs::read(request).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let mut pages = vec![];
    let mut sources = vec![];
    for (i, event) in job["events"]
        .as_array()
        .ok_or("events required")?
        .iter()
        .enumerate()
    {
        let page = rpc.call(
            "maintenance.history.page",
            json!({"scope":"own","purpose":"rebuild","event":event}),
            &stop,
        )?;
        let items = page["items"].as_array().ok_or("items missing")?;
        if items.len() != 1 || items[0]["event"] != *event {
            return Err("original source mismatch".into());
        }
        sources.push(json!({"event":event,"version":items[0]["version"],"role":if i==0{"primary"}else{"context"}}));
        pages.push(page);
    }
    let args = json!({"scope":"own","purpose":"rebuild","key":"original-route-probe","route":"extract","sources":sources});
    let open = rpc.call("maintenance.model.open", args.clone(), &stop);
    let mut preview = args;
    preview["key"] = json!("original-preview-probe");
    preview["format"] = json!("extraction");
    preview["mode"] = json!("text_json");
    let extract = rpc.call("maintenance.extract.preview", preview.clone(), &stop);
    let result =
        json!({"pages":pages,"request":preview,"model_open":open,"extract_preview":extract});
    fs::write(
        root.join("result.json"),
        serde_json::to_vec_pretty(&result).unwrap(),
    )
    .map_err(|e| e.to_string())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(std::env::var("YUKI_MAINTENANCE_PROBE")?);
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let (r, p, s) = (rpc.clone(), root.clone(), stop.clone());
    let worker = thread::spawn(move || {
        if let Err(e) = probe(r, p.clone(), s) {
            let _ = fs::write(p.join("error.txt"), e);
        }
    });
    while let Some(raw) = read_frame(&mut input)? {
        match rpc.calls.lock().unwrap().receive(&raw)? {
            Incoming::Result { id, result, .. } => {
                if let Some(tx) = rpc.pending.lock().unwrap().remove(&id) {
                    let _ = tx.send(result.map_err(|e| e.to_string()));
                }
            }
            Incoming::Call { id, .. } => {
                let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"diagnostic_peer_does_not_ack_erasure"}}));
            }
            _ => (),
        }
    }
    stop.store(true, Ordering::Release);
    worker.join().map_err(|_| "probe panicked")?;
    Ok(())
}
