//! Native message resources are addressed by the original application's token,
//! message ID, resource key and resource type. Never accept a caller-provided URL.
use crate::{Config, Error, attachment, segments, transport};
use data_encoding::BASE64;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    sync::{Arc, atomic::AtomicBool},
    time::{Duration, Instant},
};
use url::Url;

const MAX: usize = 16 * 1024 * 1024;
fn http(
    cfg: &Config,
    url: &Url,
    body: Option<&Value>,
    token: Option<&str>,
    limit: usize,
    cancelled: &AtomicBool,
) -> Result<Vec<u8>, Error> {
    let (status, bytes) = transport::request(
        cfg,
        url,
        if body.is_some() { "POST" } else { "GET" },
        body.map(transport::Body::json),
        token,
        limit,
        cancelled,
    )?;
    if status != 200 {
        return Err("resource endpoint refused".into());
    }
    Ok(bytes)
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
    cancelled: Arc<AtomicBool>,
}
impl Client {
    pub fn new(cancelled: Arc<AtomicBool>) -> Self {
        Self {
            cancelled,
            ..Self::default()
        }
    }
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
    fn token(&mut self, cfg: &Config) -> Result<String, Error> {
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
                &self.cancelled,
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
        Ok(self.token.as_ref().ok_or("no tenant token")?.0.clone())
    }
    fn reject_token(&mut self, code: &Value, original: &str) {
        if matches!(code.as_i64(), Some(99991663..=99991665))
            && self
                .token
                .as_ref()
                .is_some_and(|(token, _)| token == original)
        {
            self.token = None;
        }
    }
    pub fn upload(
        &mut self,
        cfg: &Config,
        namespace: &str,
        args: &Value,
        mime: &str,
        bytes: Vec<u8>,
    ) -> Value {
        if attachment::origin(cfg, namespace, &args["preparation_origin"]).is_err() {
            return json!({"state":"failed"});
        }
        let Ok(body) = attachment::multipart(args, mime, bytes) else {
            return json!({"state":"failed"});
        };
        let (path, key) = if args["part"]["kind"] == "image" {
            ("open-apis/im/v1/images", "image_key")
        } else {
            ("open-apis/im/v1/files", "file_key")
        };
        let Ok(url) = cfg.base.join(path) else {
            return json!({"state":"failed"});
        };
        let Ok(token) = self.token(cfg) else {
            return json!({"state":"failed"});
        };
        let Ok((status, bytes)) = transport::request(
            cfg,
            &url,
            "POST",
            Some(body),
            Some(&token),
            128 * 1024,
            &self.cancelled,
        ) else {
            return json!({"state":"unknown"});
        };
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            return json!({"state":"unknown"});
        };
        self.reject_token(&value["code"], &token);
        if (200..500).contains(&status) && value["code"].as_i64().is_some_and(|code| code != 0) {
            return json!({"state":"failed"});
        }
        if status != 200 || value["code"].as_i64() != Some(0) {
            return json!({"state":"unknown"});
        }
        match segments::native(&value["data"][key]) {
            Ok(key) => {
                json!({"state":"confirmed","resource":{"kind":args["part"]["kind"],"key":key}})
            }
            Err(_) => json!({"state":"unknown"}),
        }
    }
    pub fn effect(&mut self, cfg: &Config, namespace: &str, args: &Value, recall: bool) -> Value {
        if args.get("prepared").is_some()
            && attachment::origin(cfg, namespace, &args["prepared"]["origin"]).is_err()
        {
            return json!({"state":"failed"});
        }
        let request = if recall {
            segments::recall(cfg, args).map(|url| (url, None))
        } else {
            segments::delivery(cfg, args).map(|(url, body)| (url, Some(body)))
        };
        let Ok((url, body)) = request else {
            return json!({"state":"failed"});
        };
        let Ok(token) = self.token(cfg) else {
            return json!({"state":"failed"});
        };
        let result = transport::request(
            cfg,
            &url,
            if recall { "DELETE" } else { "POST" },
            body.as_ref().map(transport::Body::json),
            Some(&token),
            128 * 1024,
            &self.cancelled,
        );
        let Ok((status, bytes)) = result else {
            return json!({"state":"unknown"});
        };
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            return json!({"state":"unknown"});
        };
        self.reject_token(&value["code"], &token);
        if (200..500).contains(&status) && value["code"].as_i64().is_some_and(|code| code != 0) {
            return json!({"state":"failed"});
        }
        if status != 200 || value["code"].as_i64() != Some(0) {
            return json!({"state":"unknown"});
        }
        if recall {
            return json!({"state":"confirmed"});
        }
        match segments::native(&value["data"]["message_id"]) {
            Ok(native_id) => json!({"state":"confirmed", "locator":native_id}),
            Err(_) => json!({"state":"unknown"}),
        }
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
            let (status, data) =
                transport::request(cfg, &url, "GET", None, Some(&token), MAX, &self.cancelled)?;
            if status != 200 {
                if let Ok(value) = serde_json::from_slice::<Value>(&data) {
                    self.reject_token(&value["code"], &token);
                }
                return Err("resource endpoint refused".into());
            }
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
