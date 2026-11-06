//! Resolve only Telegram's original file_id, using the authenticated Bot API.
//! The Host owns event/slot authorization. This process holds one bounded transfer.
use crate::{Error, api, transport};
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::time::{Duration, Instant};

const MAX: usize = 16 * 1024 * 1024;
const PAGE: usize = 24576;
const IDLE: Duration = Duration::from_secs(30);

struct Transfer {
    key: Value,
    data: Vec<u8>,
    digest: String,
    next: usize,
    touched: Instant,
}

#[derive(Default)]
pub struct Media(Option<Transfer>);

fn file_path(path: &str) -> Result<String, Error> {
    if path.len() > 4096
        || path.contains(['\\', ':'])
        || path.chars().any(char::is_control)
        || path.split('/').any(|s| matches!(s, "" | "." | ".."))
    {
        return Err("unsafe Telegram file path".into());
    }
    let mut out = String::new();
    for b in path.bytes() {
        if b.is_ascii_alphanumeric() || b"-._~/".contains(&b) {
            out.push(b as char);
        } else {
            use std::fmt::Write;
            write!(out, "%{b:02X}")?;
        }
    }
    Ok(out)
}

impl Media {
    pub fn expire(&mut self) {
        if self.0.as_ref().is_some_and(|v| v.touched.elapsed() >= IDLE) {
            self.0 = None;
        }
    }

    pub fn page(
        &mut self,
        namespace: &str,
        bot: i64,
        base: &str,
        token: &str,
        params: &Value,
    ) -> Result<Value, Error> {
        self.expire();
        let mut key = params.clone();
        let p = key.as_object_mut().ok_or("missing media parameters")?;
        let offset = p
            .remove("offset")
            .and_then(|v| v.as_u64())
            .filter(|n| *n < MAX as u64)
            .ok_or("invalid offset")? as usize;
        let length = p
            .remove("length")
            .and_then(|v| v.as_u64())
            .filter(|n| (1..=PAGE as u64).contains(n))
            .ok_or("invalid length")? as usize;
        let transfer = params["transfer"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 128)
            .ok_or("invalid transfer")?;
        let reference = params["reference"]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 4096)
            .ok_or("invalid file_id")?;
        if params["namespace"] != namespace
            || params["platform"] != "telegram"
            || params["media_identity"] != json!({"application":bot.to_string()})
        {
            return Err("wrong original Telegram installation".into());
        }
        if self.0.is_none() {
            if offset != 0 {
                return Err("no such transfer".into());
            }
            let meta = api(base, token, "getFile", &json!({"file_id":reference}))?;
            let declared = if let Some(size) = meta.get("file_size") {
                Some(
                    size.as_u64()
                        .filter(|n| (1..=MAX as u64).contains(n))
                        .ok_or("invalid Telegram size")?,
                )
            } else {
                None
            };
            let path = file_path(meta["file_path"].as_str().ok_or("missing Telegram file")?)?;
            let url = format!("{base}/file/bot{token}/{path}");
            let data = transport::start(&url, None, MAX)?.finish()?;
            if data.is_empty() || declared.is_some_and(|n| n != data.len() as u64) {
                return Err("incomplete Telegram download".into());
            }
            let digest = format!("{:x}", Sha256::digest(&data));
            self.0 = Some(Transfer {
                key: key.clone(),
                data,
                digest,
                next: 0,
                touched: Instant::now(),
            });
        }
        let active = self.0.as_mut().ok_or("no active transfer")?;
        if active.key != key || active.next != offset {
            return Err("transfer mismatch".into());
        }
        let size = active.data.len();
        let end = (offset + length).min(size);
        let page = json!({"transfer":transfer, "offset":offset, "size":size, "sha256":active.digest,
            "data":STANDARD.encode(&active.data[offset..end])});
        active.next = end;
        active.touched = Instant::now();
        if end == size {
            self.0 = None;
        }
        Ok(page)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn platform_path_is_always_relative_to_the_same_bot() {
        assert_eq!(
            file_path("documents/雪 #%?.png").unwrap(),
            "documents/%E9%9B%AA%20%23%25%3F.png"
        );
        for path in [
            "../x",
            "folder/../file",
            "/etc/passwd",
            "https://other/file",
            "a\\b",
            "a//b",
            "x\ny",
        ] {
            assert!(file_path(path).is_err(), "{path}");
        }
    }

    #[test]
    fn abandoned_transfer_releases_its_bytes_without_another_download() {
        let mut media = Media(Some(Transfer {
            key: json!({}),
            data: vec![7; 1024],
            digest: String::new(),
            next: 1,
            touched: Instant::now() - IDLE,
        }));
        media.expire();
        assert!(media.0.is_none());
    }
}
