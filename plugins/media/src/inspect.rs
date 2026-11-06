use crate::rpc::{Result, Rpc};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Read,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
struct Decoder(Child);
impl Drop for Decoder {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
fn capture(mut stream: impl Read, limit: u64, overflow: Arc<AtomicBool>) -> Vec<u8> {
    let mut bytes = vec![];
    if stream
        .by_ref()
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .is_err()
        || bytes.len() as u64 > limit
    {
        overflow.store(true, Ordering::Release);
    }
    bytes
}
fn execute(command: &mut Command, cancel: &AtomicBool) -> Result<(Vec<u8>, Vec<u8>)> {
    let mut child = Decoder(
        command
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|_| "codec_unavailable")?,
    );
    let output = child.0.stdout.take().ok_or("codec_unavailable")?;
    let error = child.0.stderr.take().ok_or("codec_unavailable")?;
    let overflow = Arc::new(AtomicBool::new(false));
    let a = overflow.clone();
    let b = overflow.clone();
    let stdout = thread::spawn(move || capture(output, 1_048_576, a));
    let stderr = thread::spawn(move || capture(error, 262_144, b));
    let deadline = Instant::now() + Duration::from_secs(15);
    let result = loop {
        if cancel.load(Ordering::Acquire) {
            break Err("cancelled");
        }
        if overflow.load(Ordering::Acquire) {
            break Err("decoder_output_limit");
        }
        if Instant::now() >= deadline {
            break Err("decoder_timeout");
        }
        match child.0.try_wait() {
            Ok(Some(status)) => {
                break if status.success() {
                    Ok(())
                } else {
                    Err("document_unreadable")
                };
            }
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(_) => break Err("decoder_failed"),
        }
    };
    drop(child);
    let out = stdout.join().map_err(|_| "decoder_failed")?;
    let err = stderr.join().map_err(|_| "decoder_failed")?;
    result.map_err(str::to_owned)?;
    if overflow.load(Ordering::Acquire) {
        return Err("decoder_output_limit".into());
    }
    Ok((out, err))
}

fn configured(name: &str) -> Result<PathBuf> {
    let path = PathBuf::from(std::env::var_os(name).ok_or("codec_unavailable")?);
    if !path.is_absolute() || !path.is_file() {
        return Err("codec_unavailable".into());
    }
    Ok(path)
}
fn pdf(dir: &Path, cancel: &AtomicBool) -> Result<Value> {
    let path = dir.join("input.pdf");
    let parser = std::env::current_exe()
        .map_err(|_| "codec_unavailable")?
        .parent()
        .ok_or("codec_unavailable")?
        .join("backend/document_reader.py");
    let pin: Value = serde_json::from_str(include_str!("../backend/source.lock.json"))
        .map_err(|_| "codec_pin_invalid")?;
    if digest(&fs::read(&parser).map_err(|_| "codec_unavailable")?)
        != pin["sha256"].as_str().ok_or("codec_pin_invalid")?
    {
        return Err("codec_digest_mismatch".into());
    }
    let mut cmd = Command::new(configured("YUKI_MEDIA_PYTHON")?);
    cmd.current_dir(dir).args(["-I","-c",
        "import importlib.metadata,runpy,sys; assert importlib.metadata.version('pypdf')=='6.18.0'; assert importlib.metadata.version('defusedxml')=='0.7.1'; p=sys.argv.pop(1); runpy.run_path(p,run_name='__main__')"])
        .arg(parser).arg(path).args([".pdf","24000","12"]);
    let (out, _) = execute(&mut cmd, cancel)?;
    let value: Value = serde_json::from_slice(&out).map_err(|_| "decoder_invalid_result")?;
    if let Some(error) = value["error"].as_str() {
        return Err(error.to_owned());
    }
    if value["kind"] != "pdf" {
        return Err("decoder_invalid_result".into());
    }
    let has_text = value["text"].as_str().unwrap_or("").lines().any(|line| {
        let line = line.trim();
        !line.is_empty()
            && !(line.starts_with("[page ") && line.ends_with(']'))
            && !line.starts_with("[PDF text extraction only;")
    });
    if !has_text {
        return Err("document_empty".into());
    }
    Ok(value)
}

fn video(dir: &Path, cancel: &AtomicBool) -> Result<Vec<(f64, Vec<u8>)>> {
    let exe = configured("YUKI_MEDIA_FFMPEG")?;
    let lock: Value = serde_json::from_str(include_str!("../packaging/codecs.lock"))
        .map_err(|_| "codec_pin_invalid")?;
    let target = format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH);
    let expected = lock["ffmpeg"]["platforms"][target]["binary_sha256"]
        .as_str()
        .ok_or("codec_target_unavailable")?;
    if digest(&fs::read(&exe).map_err(|_| "codec_unavailable")?) != expected {
        return Err("codec_digest_mismatch".into());
    }
    let mut cmd = Command::new(exe);
    cmd.current_dir(dir).args([
        "-nostdin",
        "-hide_banner",
        "-v",
        "info",
        "-max_alloc",
        "33554432",
        "-threads",
        "1",
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        "mov,matroska,webm",
        "-i",
        "input.video",
        "-an",
        "-sn",
        "-t",
        "600",
        "-vf",
        "select='eq(n,0)+gte(t-prev_selected_t,5)',scale=w='min(1024,iw)':h=-2,showinfo",
        "-vsync",
        "vfr",
        "-frames:v",
        "8",
        "-threads",
        "1",
        "frame-%02d.png",
    ]);
    let (_, err) = execute(&mut cmd, cancel)?;
    let times: Vec<f64> = String::from_utf8_lossy(&err)
        .lines()
        .filter_map(|line| {
            if !line.contains("showinfo") {
                return None;
            }
            line.split("pts_time:")
                .nth(1)?
                .split_whitespace()
                .next()?
                .parse::<f64>()
                .ok()
        })
        .collect();
    let mut frames = vec![];
    for (index, time) in times.into_iter().take(8).enumerate() {
        if !time.is_finite() || time < 0.0 {
            return Err("invalid_frame_time".into());
        }
        let path = dir.join(format!("frame-{:02}.png", index + 1));
        if fs::metadata(&path).map_err(|_| "video_unreadable")?.len() > 2_097_152 {
            return Err("frame_limit".into());
        }
        let bytes = fs::read(path).map_err(|_| "video_unreadable")?;
        if !bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
            return Err("video_unreadable".into());
        }
        frames.push((time, bytes));
    }
    if frames.is_empty() {
        return Err("video_unreadable".into());
    }
    Ok(frames)
}

fn read(rpc: &Rpc, handle: &str, cancel: &AtomicBool) -> Result<(String, Vec<u8>)> {
    let mut bytes = vec![];
    let mut version = None;
    let mut total = None;
    loop {
        let r = rpc.call(
            "media.open",
            json!({"handle":handle,"offset":bytes.len(),"length":16384}),
            cancel,
        )?;
        let length = r["total"]
            .as_u64()
            .filter(|n| *n <= 16_777_216)
            .ok_or("invalid_source_length")?;
        let v = r["version"].as_str().ok_or("invalid_source_version")?;
        if total.is_some_and(|n| n != length)
            || version.as_deref().is_some_and(|s| s != v)
            || r["offset"].as_u64() != Some(bytes.len() as u64)
        {
            return Err("source_changed".into());
        }
        total = Some(length);
        version = Some(v.to_owned());
        let chunk = STANDARD
            .decode(r["bytes"].as_str().ok_or("invalid_source_chunk")?)
            .map_err(|_| "invalid_source_chunk")?;
        if chunk.len() > 16384 || bytes.len() + chunk.len() > length as usize {
            return Err("invalid_source_chunk".into());
        }
        if chunk.is_empty() && bytes.len() < length as usize {
            return Err("incomplete_source".into());
        }
        bytes.extend(chunk);
        if r["done"] == true {
            if bytes.len() != length as usize || digest(&bytes) != v {
                return Err("source_digest_mismatch".into());
            }
            return Ok((v.to_owned(), bytes));
        }
        if bytes.len() >= length as usize {
            return Err("invalid_source_end".into());
        }
    }
}
fn check(rpc: &Rpc, handle: &str, version: &str, cancel: &AtomicBool) -> Result<()> {
    let r = rpc.call(
        "media.open",
        json!({"handle":handle,"offset":0,"length":1}),
        cancel,
    )?;
    if r["version"] != version {
        return Err("source_changed".into());
    }
    Ok(())
}
fn decode(rpc: &Rpc, p: &Value, cancel: &AtomicBool, dir: &Path) -> Result<Value> {
    let handle = p["handle"].as_str().ok_or("invalid_call")?;
    let purpose = p["arguments"]["purpose"]
        .as_str()
        .ok_or("invalid_purpose")?;
    if !matches!(purpose, "inspect" | "frames") {
        return Err("unsupported_purpose".into());
    }
    let (version, bytes) = read(rpc, handle, cancel)?;
    let source = p["arguments"]["media"].clone();
    if bytes.starts_with(b"%PDF-") && purpose == "inspect" {
        fs::write(dir.join("input.pdf"), bytes).map_err(|_| "temporary_write_failed")?;
        let mut result = pdf(dir, cancel)?;
        check(rpc, handle, &version, cancel)?;
        result["source"] = source;
        result["version"] = json!(version);
        result["state"] = json!("read");
        return Ok(result);
    }
    if !(bytes.get(4..8) == Some(b"ftyp") || bytes.starts_with(&[0x1a, 0x45, 0xdf, 0xa3])) {
        return Err("unsupported_or_corrupt_document".into());
    }
    fs::write(dir.join("input.video"), bytes).map_err(|_| "temporary_write_failed")?;
    let frames = video(dir, cancel)?;
    check(rpc, handle, &version, cancel)?;
    let mut images = vec![];
    let mut positions = vec![];
    for (index, (time, bytes)) in frames.into_iter().enumerate() {
        let hash = digest(&bytes);
        let mut last = Value::Null;
        for (chunk, part) in bytes.chunks(16384).enumerate() {
            last=rpc.call("media.publish",json!({"handle":handle,"key":format!("frame-{index}"),
                "filename":format!("frame-{index}.png"),"kind":"image","mime":"image/png","digest":hash,
                "size":bytes.len(),"offset":chunk*16384,"bytes":STANDARD.encode(part)}),cancel)?;
            if last["next_offset"].as_u64() != Some((chunk * 16384 + part.len()) as u64) {
                return Err("incomplete_publication".into());
            }
        }
        if last["complete"] != true || last["version"] != hash || !last["artifact_id"].is_string() {
            return Err("incomplete_publication".into());
        }
        images.push(json!({"artifact_id":last["artifact_id"],"version":last["version"]}));
        positions.push(json!({"index":index,"seconds":time,"sha256":hash}));
    }
    check(rpc, handle, &version, cancel)?;
    Ok(
        json!({"state":"read","kind":"video","source":source,"version":version,"images":images,"frames":positions,"limit_frames":8,"limit_seconds":600}),
    )
}
pub fn process(rpc: &Rpc, p: &Value, cancel: &AtomicBool) -> Result<Value> {
    let parent = std::env::var_os("YUKI_MEDIA_TEMP")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let dir = tempfile::Builder::new()
        .prefix("yuki-media-")
        .tempdir_in(parent)
        .map_err(|_| "temporary_directory_failed")?;
    let result = decode(rpc, p, cancel, dir.path());
    dir.close().map_err(|_| "temporary_cleanup_failed")?;
    result
}
