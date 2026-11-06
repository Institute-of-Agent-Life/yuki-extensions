//! A bounded curl pipe. Credentials never enter argv, logs or response errors.
use crate::Error;
use std::{
    io::{Read, Write},
    process::{Child, Command, Stdio},
    thread::{self, JoinHandle},
};

pub struct Request {
    child: Child,
    reader: Option<JoinHandle<std::io::Result<Vec<u8>>>>,
    limit: usize,
}

impl Request {
    pub fn ready(&mut self) -> Result<bool, Error> {
        Ok(self.child.try_wait()?.is_some())
    }

    pub fn finish(mut self) -> Result<Vec<u8>, Error> {
        let ok = self.child.wait()?.success();
        let mut data = self
            .reader
            .take()
            .ok_or("missing Telegram pipe")?
            .join()
            .map_err(|_| "Telegram pipe closed")??;
        if !ok || data.len() < 3 || data.len() > self.limit + 3 || !data.ends_with(b"200") {
            return Err("Telegram transport failed".into());
        }
        data.truncate(data.len() - 3);
        Ok(data)
    }
}

impl Drop for Request {
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

pub fn start(url: &str, post: Option<&serde_json::Value>, limit: usize) -> Result<Request, Error> {
    let mut child = Command::new("curl")
        .args([
            "--disable",
            "--silent",
            "--globoff",
            "--max-time",
            "40",
            "--max-filesize",
            &limit.to_string(),
            "--write-out",
            "%{http_code}",
            "--config",
            "-",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let stdout = child.stdout.take().ok_or("missing Telegram stdout")?;
    let mut req = Request {
        child,
        reader: Some(thread::spawn(move || {
            let mut bytes = Vec::new();
            stdout.take(limit as u64 + 4).read_to_end(&mut bytes)?;
            Ok(bytes)
        })),
        limit,
    };
    let mut stdin = req.child.stdin.take().ok_or("missing Telegram stdin")?;
    writeln!(stdin, "url = \"{url}\"")?;
    if let Some(params) = post {
        let form = params
            .to_string()
            .replace('\\', "\\\\")
            .replace('"', "\\\"");
        writeln!(
            stdin,
            "header = \"Content-Type: application/json\"\ndata = \"{form}\""
        )?;
    }
    Ok(req)
}
