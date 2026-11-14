mod hygiene;
mod rebuild;
mod reflection;
mod rpc;
mod schedule;
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

#[derive(Clone, Copy, PartialEq, Eq)]
enum Mode {
    Quality,
    RetainedQuality,
    Rebuild,
    Reflection,
    ScheduledReflection,
}

fn job_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 80
        && name.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
}

fn safe_job(path: &std::path::Path) -> bool {
    path.extension().is_some_and(|s| s == "job")
        && path
            .file_stem()
            .and_then(|s| s.to_str())
            .is_some_and(job_name)
}
fn run_jobs(
    rpc: Arc<rpc::Rpc>,
    root: PathBuf,
    mode: Mode,
    stop: Arc<AtomicBool>,
) -> Result<(), String> {
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
            if started.exists() || output.exists() {
                continue;
            }
            if fs::metadata(&path).map_err(|e| e.to_string())?.len() > 32768 {
                continue;
            }
            let raw = fs::read(&path).map_err(|e| e.to_string())?;
            let request = serde_json::from_slice::<Value>(&raw).map_err(|e| e.to_string());
            let mut marker = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&started)
                .map_err(|e| e.to_string())?;
            marker
                .write_all(b"submitted; inspect original operation before manual recovery\n")
                .and_then(|_| marker.sync_all())
                .map_err(|e| e.to_string())?;
            let result = request.and_then(|job| {
                let key = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .ok_or("invalid job name")?;
                if mode == Mode::Reflection {
                    return reflection::run(&root, key, job, |method, params| {
                        rpc.call(method, params, &stop)
                    })
                    .map(|body| (body, None));
                }
                let rebuild_job = job["action"]
                    .as_str()
                    .is_some_and(|action| action.starts_with("rebuild."));
                if mode == Mode::Rebuild && rebuild_job {
                    return rebuild::run(&root, key, job, |method, params| {
                        rpc.call(method, params, &stop)
                    })
                    .map(|body| (body, None));
                }
                if mode == Mode::Rebuild || rebuild_job {
                    return Err("job does not match the installed maintenance mode".into());
                }
                let (method, mut params) = hygiene::request(&job)?;
                let integrity_requested = params["integrity"] == true;
                if mode == Mode::RetainedQuality {
                    params["retain"] = json!(true);
                }
                let response = rpc.call(method, params, &stop)?;
                let refs = (mode == Mode::RetainedQuality)
                    .then(|| hygiene::bind_result(method, &response))
                    .transpose()?;
                let body = if method == "maintenance.audit" {
                    hygiene::scan_report(response, integrity_requested)?
                } else {
                    response
                };
                Ok((body, refs))
            });
            if stop.load(Ordering::Acquire) {
                break;
            }
            let report = match result {
                Ok((value, Some(refs))) => {
                    json!({"state":"completed","result":value,"erasure_refs":refs})
                }
                Ok((value, None)) => json!({"state":"completed","result":value}),
                Err(e) => {
                    json!({"state":"not_completed","error":e,"retry":"explicit original-operation recovery only"})
                }
            };
            if mode != Mode::Quality {
                rebuild::write_json(&output, &report)?;
            } else {
                let mut file = OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(output)
                    .map_err(|e| e.to_string())?;
                file.write_all(serde_json::to_string_pretty(&report).unwrap().as_bytes())
                    .and_then(|_| file.sync_all())
                    .map_err(|e| e.to_string())?;
            }
        }
        thread::sleep(Duration::from_millis(100));
    }
    Ok(())
}

fn run_schedule(
    rpc: Arc<rpc::Rpc>,
    root: PathBuf,
    stop: Arc<AtomicBool>,
    schedule: schedule::Schedule,
) -> Result<(), String> {
    while !stop.load(Ordering::Acquire) {
        schedule.poll(
            &root,
            std::time::SystemTime::now().into(),
            |method, params| rpc.call(method, params, &stop),
        )?;
        for _ in 0..10 {
            if stop.load(Ordering::Acquire) {
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
    }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(std::env::var("YUKI_MEMORY_MAINTENANCE_JOBS")?).canonicalize()?;
    if !root.is_dir() {
        return Err("private operator job directory required".into());
    }
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    let mode = match args.as_slice() {
        [] => Mode::Quality,
        [mode] if mode == "--rebuild-only" => Mode::Rebuild,
        [mode] if mode == "--retain-reports" => Mode::RetainedQuality,
        [mode] if mode == "--reflection-only" => Mode::Reflection,
        [mode] if mode == "--scheduled-reflection" => Mode::ScheduledReflection,
        _ => return Err("unsupported maintenance worker mode".into()),
    };
    let _lock = (mode != Mode::Quality)
        .then(|| rebuild::lock(&root))
        .transpose()?;
    let erasure_only = std::env::var("YUKI_PLUGIN_START_MODE").as_deref() == Ok("erasure_only");
    let schedule = (mode == Mode::ScheduledReflection && !erasure_only)
        .then(|| schedule::Schedule::load(&root))
        .transpose()?;
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let stop = Arc::new(AtomicBool::new(false));
    let (r, p, s) = (rpc.clone(), root.clone(), stop.clone());
    let mut worker = (!erasure_only).then(|| {
        thread::spawn(move || match schedule {
            Some(schedule) => run_schedule(r, p, s, schedule),
            None => run_jobs(r, p, mode, s),
        })
    });
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
                let erased = if !joined {
                    Err("worker_stop_failed")
                } else {
                    match mode {
                        Mode::Rebuild => rebuild::erase(&root, &params["sources"])
                            .map(|()| "selected rebuild state and results removed")
                            .map_err(|_| "rebuild_erasure_incomplete"),
                        Mode::RetainedQuality => hygiene::erase(&root, &params)
                            .map(|()| "selected quality reports removed")
                            .map_err(|_| "quality_erasure_incomplete"),
                        Mode::Reflection => reflection::erase(&root, &params["sources"])
                            .map(|()| "matching reflection state and results removed")
                            .map_err(|_| "reflection_erasure_incomplete"),
                        Mode::ScheduledReflection => reflection::erase(&root, &params["sources"])
                            .and_then(|()| schedule::erase(&root, &params["sources"]))
                            .map(|()| "matching scheduled reflection state and results removed")
                            .map_err(|_| "reflection_erasure_incomplete"),
                        Mode::Quality => Err("metadata_erasure_contract_pending"),
                    }
                };
                let reply = match erased {
                    Ok(proof) => {
                        json!({"jsonrpc":"2.0","id":id,"result":{"key":params["key"],"watermark":params["watermark"],"proof":proof}})
                    }
                    Err(message) => {
                        json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":message}})
                    }
                };
                let _ = rpc.send(&reply);
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
