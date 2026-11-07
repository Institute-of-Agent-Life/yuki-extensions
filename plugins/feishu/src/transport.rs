//! Bounded regional REST pipe, cancelled and joined before private state is cleared.
use crate::{Config, Error};
use serde_json::Value;
use std::{
    io::{Read, Write},
    process::{Child, Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    thread::{self, JoinHandle},
    time::Duration,
};
use url::Url;

struct Pipe {
    child: Child,
    reader: Option<JoinHandle<std::io::Result<Vec<u8>>>>,
}

impl Drop for Pipe {
    fn drop(&mut self) {
        if !matches!(self.child.try_wait(), Ok(Some(_))) {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
    }
}

pub fn request(
    cfg: &Config,
    url: &Url,
    method: &str,
    body: Option<&Value>,
    token: Option<&str>,
    limit: usize,
    cancelled: &AtomicBool,
) -> Result<(u16, Vec<u8>), Error> {
    if cancelled.load(Ordering::SeqCst) {
        return Err("request cancelled".into());
    }
    // curl 8.3+ expands these child-only values without placing secrets or native IDs in argv.
    // The body uses binary stdin, independent of curl's configuration-line parser.
    let input = body.map(Value::to_string).unwrap_or_default().into_bytes();
    let mut command =
        Command::new(std::env::var_os("YUKI_FEISHU_CURL").unwrap_or_else(|| "curl".into()));
    command.env("YUKI_FEISHU_REQUEST_URL", url.as_str());
    command.args([
        "--disable",
        "--silent",
        "--globoff",
        "--max-time",
        "12",
        "--max-filesize",
        &limit.to_string(),
        "--write-out",
        "%{http_code}",
        "--variable",
        "%YUKI_FEISHU_REQUEST_URL",
        "--expand-url",
        "{{YUKI_FEISHU_REQUEST_URL}}",
        "--request",
        method,
    ]);
    if body.is_some() {
        command.args([
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ]);
    }
    if let Some(token) = token {
        if token.is_empty()
            || !token.is_ascii()
            || token
                .bytes()
                .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
        {
            return Err("invalid request token".into());
        }
        command.env("YUKI_FEISHU_REQUEST_TOKEN", token).args([
            "--variable",
            "%YUKI_FEISHU_REQUEST_TOKEN",
            "--expand-header",
            "Authorization: Bearer {{YUKI_FEISHU_REQUEST_TOKEN}}",
        ]);
    }
    if let Some(proxy) = &cfg.proxy {
        command
            .env("https_proxy", proxy.as_str())
            .env("http_proxy", proxy.as_str())
            .env("no_proxy", "");
    } else {
        command.args(["--noproxy", "*"]);
    }
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let mut stdin = child.stdin.take().ok_or("missing request pipe")?;
    let stdout = child.stdout.take().ok_or("missing response pipe")?;
    let reader = thread::spawn(move || {
        let writer = thread::spawn(move || stdin.write_all(&input));
        let mut bytes = Vec::new();
        let read = stdout.take(limit as u64 + 4).read_to_end(&mut bytes);
        writer
            .join()
            .map_err(|_| std::io::Error::other("request pipe closed"))??;
        read?;
        Ok(bytes)
    });
    let mut pipe = Pipe {
        child,
        reader: Some(reader),
    };
    let status = loop {
        if cancelled.load(Ordering::SeqCst) {
            return Err("request cancelled".into());
        }
        if let Some(status) = pipe.child.try_wait()? {
            break status;
        }
        thread::sleep(Duration::from_millis(20));
    };
    let mut bytes = pipe
        .reader
        .take()
        .ok_or("missing reader")?
        .join()
        .map_err(|_| "response pipe closed")??;
    if !status.success() || bytes.len() < 3 || bytes.len() > limit + 3 {
        return Err("REST transport failed".into());
    }
    let code = std::str::from_utf8(&bytes[bytes.len() - 3..])?.parse()?;
    bytes.truncate(bytes.len() - 3);
    Ok((code, bytes))
}
