//! Native message resources are addressed by the original application's token,
//! message ID, resource key and resource type. Never accept a caller-provided URL.
use crate::{Config, Error};
use data_encoding::BASE64;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    process::{Command, Stdio},
    time::{Duration, Instant},
};
use url::Url;

const MAX: usize = 16 * 1024 * 1024;
fn config_value(s: &str) -> Result<String, Error> {
    if s.chars().any(char::is_control) {
        return Err("invalid request".into());
    }
    Ok(s.replace('\\', "\\\\").replace('"', "\\\""))
}
fn http(
    cfg: &Config,
    url: &Url,
    body: Option<&Value>,
    token: Option<&str>,
    limit: usize,
) -> Result<Vec<u8>, Error> {
    let mut config = format!("url = \"{}\"\n", config_value(url.as_str())?);
    if let Some(v) = body {
        config.push_str(&format!(
            "header = \"Content-Type: application/json\"\ndata = \"{}\"\n",
            config_value(&v.to_string())?
        ));
    }
    if let Some(t) = token {
        config.push_str(&format!(
            "header = \"Authorization: Bearer {}\"\n",
            config_value(t)?
        ));
    }
    let mut cmd = Command::new("curl");
    cmd.args([
        "--disable",
        "--silent",
        "--globoff",
        "--max-time",
        "12",
        "--max-filesize",
        &limit.to_string(),
        "--write-out",
        "%{http_code}",
        "--config",
        "-",
    ]);
    if let Some(p) = &cfg.proxy {
        cmd.env("https_proxy", p.as_str())
            .env("http_proxy", p.as_str())
            .env("no_proxy", "");
    } else {
        cmd.args(["--noproxy", "*"]);
    }
    let mut child = cmd
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let result = (|| -> Result<Vec<u8>, Error> {
        child
            .stdin
            .take()
            .ok_or("missing pipe")?
            .write_all(config.as_bytes())?;
        let mut bytes = Vec::new();
        child
            .stdout
            .take()
            .ok_or("missing pipe")?
            .take(limit as u64 + 4)
            .read_to_end(&mut bytes)?;
        if !child.wait()?.success()
            || bytes.len() < 3
            || bytes.len() > limit + 3
            || !bytes.ends_with(b"200")
        {
            return Err("resource endpoint refused".into());
        }
        bytes.truncate(bytes.len() - 3);
        Ok(bytes)
    })();
    if !matches!(child.try_wait(), Ok(Some(_))) {
        let _ = child.kill();
    }
    let _ = child.wait();
    result
}

fn resource(cfg: &Config, p: &Value) -> Result<Url, Error> {
    let msg = p["locator"]["native_id"]
        .as_str()
        .ok_or("no original message")?;
    // The installed ingress uses the message ID as both native ID and source.
    if p["locator"]["source"] != msg {
        return Err("wrong original message".into());
    }
    let key = p["reference"].as_str().ok_or("missing key")?;
    if [msg, key].iter().any(|x| {
        x.is_empty()
            || x.len() > 4096
            || x.chars().any(char::is_control)
            || matches!(*x, "." | "..")
    }) {
        return Err("invalid resource locator".into());
    }
    let ty = match p["kind"].as_str() {
        Some("image") => "image",
        Some("file" | "audio" | "video") => "file",
        _ => return Err("unsupported resource".into()),
    };
    let mut url = cfg.base.join("open-apis/im/v1/messages/")?;
    url.path_segments_mut()
        .map_err(|_| "invalid origin")?
        .pop_if_empty()
        .push(msg)
        .push("resources")
        .push(key);
    url.query_pairs_mut().append_pair("type", ty);
    Ok(url)
}

struct Page {
    key: Value,
    data: Vec<u8>,
    digest: String,
    next: usize,
    touched: Instant,
}
#[derive(Default)]
pub struct Client {
    token: Option<(String, Instant)>,
    page: Option<Page>,
}
impl Client {
    pub fn expire(&mut self) {
        if self
            .page
            .as_ref()
            .is_some_and(|p| p.touched.elapsed() >= Duration::from_secs(30))
        {
            self.page = None;
        }
        if self
            .token
            .as_ref()
            .is_some_and(|(_, exp)| Instant::now() >= *exp)
        {
            self.token = None;
        }
    }
    fn token(&mut self, cfg: &Config) -> Result<&str, Error> {
        self.expire();
        if self.token.is_none() {
            let payload = json!({"app_id":cfg.app,"app_secret":cfg.secret});
            let b = http(
                cfg,
                &cfg.base
                    .join("open-apis/auth/v3/tenant_access_token/internal")?,
                Some(&payload),
                None,
                65536,
            )?;
            let v: Value = serde_json::from_slice(&b)?;
            if v["code"].as_i64() != Some(0) {
                return Err("tenant authentication refused".into());
            }
            let t = v["tenant_access_token"]
                .as_str()
                .filter(|s| {
                    !s.is_empty()
                        && s.is_ascii()
                        && !s
                            .bytes()
                            .any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
                })
                .ok_or("invalid tenant token")?;
            let ttl = v["expire"]
                .as_u64()
                .filter(|n| *n > 0)
                .ok_or("invalid expiry")?;
            let until = Instant::now()
                .checked_add(Duration::from_secs(ttl))
                .ok_or("invalid expiry")?;
            self.token = Some((t.into(), until));
        }
        Ok(&self.token.as_ref().ok_or("no tenant token")?.0)
    }
    pub fn chunk(&mut self, cfg: &Config, namespace: &str, params: Value) -> Result<Value, Error> {
        self.expire();
        if params["namespace"] != namespace
            || params["platform"] != cfg.domain
            || params["media_identity"] != json!({"application":cfg.app,"tenant":cfg.tenant})
        {
            return Err("wrong resource installation".into());
        }
        let mut key = params;
        let p = key.as_object_mut().ok_or("missing parameters")?;
        let offset = p
            .remove("offset")
            .and_then(|v| v.as_u64())
            .filter(|n| *n < MAX as u64)
            .ok_or("invalid offset")? as usize;
        let len = p
            .remove("length")
            .and_then(|v| v.as_u64())
            .filter(|n| (1..=24576).contains(n))
            .ok_or("invalid page")? as usize;
        let transfer = key["transfer"]
            .as_str()
            .filter(|t| !t.is_empty() && t.len() <= 128)
            .ok_or("no transfer")?;
        if self.page.is_none() {
            if offset != 0 {
                return Err("no such transfer".into());
            }
            let url = resource(cfg, &key)?;
            let token = self.token(cfg)?;
            let data = http(cfg, &url, None, Some(token), MAX)?;
            if data.is_empty() {
                return Err("empty resource".into());
            }
            let digest = format!("{:x}", Sha256::digest(&data));
            self.page = Some(Page {
                key: key.clone(),
                data,
                digest,
                next: 0,
                touched: Instant::now(),
            });
        }
        let page = self.page.as_mut().ok_or("no transfer")?;
        if page.key != key || page.next != offset {
            return Err("wrong transfer or offset".into());
        }
        let size = page.data.len();
        let end = (offset + len).min(size);
        let result = json!({"transfer":transfer,"offset":offset,"size":size,"sha256":page.digest,"data":BASE64.encode(&page.data[offset..end])});
        page.next = end;
        page.touched = Instant::now();
        if size == end {
            self.page = None;
        }
        Ok(result)
    }
}
