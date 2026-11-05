mod hygiene;
mod rpc;
use serde_json::{Value, json};
use std::{
    fs,
    fs::OpenOptions,
    io,
    io::Write,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::Duration,
};
use yuki_plugin_sdk::{host::Incoming, read_frame};

fn safe_job(path: &std::path::Path) -> bool {
    path.extension().is_some_and(|s| s == "job")
        && path.file_stem().and_then(|s| s.to_str()).is_some_and(|s| {
            !s.is_empty()
                && s.len() <= 80
                && s.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
        })
}
fn run_jobs(rpc: Arc<rpc::Rpc>, root: PathBuf, stop: Arc<AtomicBool>) -> Result<(), String> {
    while !stop.load(Ordering::Acquire) {
        let mut paths: Vec<_> = fs::read_dir(&root)
            .map_err(|e| e.to_string())?
            .filter_map(Result::ok)
            .map(|e| e.path())
            .filter(|p| safe_job(p))
            .collect();
        paths.sort();
        for path in paths {
            if stop.load(Ordering::Acquire) {
                break;
            }
            if fs::symlink_metadata(&path)
                .map_err(|e| e.to_string())?
                .file_type()
                .is_symlink()
            {
                continue;
            }
            let started = path.with_extension("started");
            let output = path.with_extension("result");
            // A durable started marker fences automatic retry after an unknown result.
            if started.exists() {
                continue;
            }
            if fs::metadata(&path).map_err(|e| e.to_string())?.len() > 32768 {
                continue;
            }
            let raw = fs::read(&path).map_err(|e| e.to_string())?;
            let request = serde_json::from_slice::<Value>(&raw)
                .map_err(|e| e.to_string())
                .and_then(|job| hygiene::request(&job));
            let mut marker = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&started)
                .map_err(|e| e.to_string())?;
            marker
                .write_all(b"submitted; inspect original operation before manual recovery\n")
                .and_then(|_| marker.sync_all())
                .map_err(|e| e.to_string())?;
            let result = request.and_then(|(method, params)| {
                rpc.call(method, params, &stop).and_then(|r| {
                    if method == "maintenance.audit" { hygiene::scan_report(r) } else { Ok(r) }
                })
            });
            if stop.load(Ordering::Acquire) {
                break;
            }
            let report = match result {
                Ok(value) => json!({"state":"completed","result":value}),
                Err(e) => {
                    json!({"state":"not_completed","error":e,"retry":"explicit original-operation recovery only"})
                }
            };
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(output)
                .map_err(|e| e.to_string())?;
            file.write_all(serde_json::to_string_pretty(&report).unwrap().as_bytes())
                .and_then(|_| file.sync_all())
                .map_err(|e| e.to_string())?;
        }
        thread::sleep(Duration::from_millis(100));
    }
    Ok(())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(std::env::var("YUKI_MEMORY_MAINTENANCE_JOBS")?).canonicalize()?;
    if !root.is_dir() {
        return Err("private operator job directory required".into());
    }
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let (r, p, s) = (rpc.clone(), root.clone(), stop.clone());
    let mut worker = Some(thread::spawn(move || run_jobs(r, p, s)));
    while let Some(raw) = read_frame(&mut input)? {
        let frame = rpc.calls.lock().unwrap().receive(&raw)?;
        match frame {
            Incoming::Result { id, result, .. } => {
                if let Some(tx) = rpc.pending.lock().unwrap().remove(&id) {
                    let _ = tx.send(result.map_err(|e| e.to_string()));
                }
            }
            Incoming::Call { method, id, params } if method == "forget.request" => {
                stop.store(true, Ordering::Release);
                let joined = worker
                    .take()
                    .is_none_or(|w| w.join().is_ok_and(|r| r.is_ok()));
                // Audit has no source-dependency projection. Do not erase unrelated
                // operator jobs or acknowledge a source cleanup we cannot establish.
                let _ = params;
                let message = if joined { "metadata_erasure_contract_pending" } else { "worker_stop_failed" };
                let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":message}}));
            }
            Incoming::Call { id, .. } => {
                let _=rpc.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"operator_jobs_only"}}));
            }
            Incoming::Notification { .. } => (),
        }
    }
    stop.store(true, Ordering::Release);
    if let Some(w) = worker {
        w.join().map_err(|_| "worker panicked")??;
    }
    Ok(())
}
