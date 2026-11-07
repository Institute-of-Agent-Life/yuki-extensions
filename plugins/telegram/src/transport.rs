//! A bounded curl pipe. Credentials never enter argv, logs or response errors.
use crate::Error;
use sha2::{Digest, Sha256};
use std::{
    env,
    io::{Read, Write},
    process::{Child, Command, Stdio},
    thread::{self, JoinHandle},
};

fn curl() -> Command {
    Command::new(env::var_os("YUKI_TELEGRAM_CURL").unwrap_or_else(|| "curl".into()))
}

pub struct Request {
    child: Child,
    reader: Option<JoinHandle<std::io::Result<Vec<u8>>>>,
    limit: usize,
}

impl Request {
    pub fn ready(&mut self) -> Result<bool, Error> {
        Ok(self.child.try_wait()?.is_some())
    }

    pub fn response(mut self) -> Result<(u16, Vec<u8>), Error> {
        let ok = self.child.wait()?.success();
        let mut data = self
            .reader
            .take()
            .ok_or("missing Telegram pipe")?
            .join()
            .map_err(|_| "Telegram pipe closed")??;
        if !ok || data.len() < 3 || data.len() > self.limit + 3 {
            return Err("Telegram transport failed".into());
        }
        let status = std::str::from_utf8(&data[data.len() - 3..])?.parse()?;
        data.truncate(data.len() - 3);
        Ok((status, data))
    }

    pub fn finish(self) -> Result<Vec<u8>, Error> {
        let (status, data) = self.response()?;
        if status != 200 {
            return Err("Telegram transport failed".into());
        }
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
    let mut child = curl()
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

/// Pass the installed token through curl's environment variable expansion and the
/// UTF-8 multipart body through a pipe. Neither is stored in a file or process arguments.
#[allow(clippy::too_many_arguments)]
pub fn upload(
    base: &str,
    method: &str,
    field: &str,
    chat: &str,
    topic: Option<i64>,
    name: &str,
    mime: &str,
    caption: Option<&str>,
    reply: Option<i64>,
    bytes: Vec<u8>,
) -> Result<Request, Error> {
    let limit = 128 * 1024;
    let boundary = format!("yuki-{:x}", Sha256::digest(&bytes));
    if bytes
        .windows(boundary.len())
        .any(|part| part == boundary.as_bytes())
        || caption.is_some_and(|text| text.contains(&boundary))
    {
        return Err("multipart boundary occurs in attachment".into());
    }
    let mut body = Vec::new();
    write!(
        body,
        "--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n"
    )?;
    if let Some(topic) = topic {
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"message_thread_id\"\r\n\r\n{topic}\r\n"
        )?;
    }
    if let Some(message) = reply {
        let parameters =
            serde_json::json!({"message_id":message,"allow_sending_without_reply":false});
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"reply_parameters\"\r\n\r\n{parameters}\r\n"
        )?;
    }
    if let Some(caption) = caption {
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{caption}\r\n"
        )?;
    }
    write!(
        body,
        "--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{name}\"\r\nContent-Type: {mime}\r\n\r\n"
    )?;
    body.extend_from_slice(&bytes);
    write!(body, "\r\n--{boundary}--\r\n")?;
    let mut cmd = curl();
    cmd.args([
        "--disable",
        "--silent",
        "--globoff",
        "--max-time",
        "40",
        "--max-filesize",
        &limit.to_string(),
        "--write-out",
        "%{http_code}",
        "--variable",
        "%YUKI_TELEGRAM_TOKEN",
        "--expand-url",
        &format!("{base}/bot{{{{YUKI_TELEGRAM_TOKEN}}}}/{method}"),
        "--header",
        &format!("Content-Type: multipart/form-data; boundary={boundary}"),
        "--data-binary",
        "@-",
    ]);
    let mut child = cmd
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let mut stdin = child.stdin.take().ok_or("missing upload pipe")?;
    let stdout = child.stdout.take().ok_or("missing upload response")?;
    let reader = thread::spawn(move || {
        let writer = thread::spawn(move || stdin.write_all(&body));
        let mut body = Vec::new();
        let read = stdout.take(limit as u64 + 4).read_to_end(&mut body);
        writer
            .join()
            .map_err(|_| std::io::Error::other("upload pipe closed"))??;
        read?;
        Ok(body)
    });
    Ok(Request {
        child,
        reader: Some(reader),
        limit,
    })
}
