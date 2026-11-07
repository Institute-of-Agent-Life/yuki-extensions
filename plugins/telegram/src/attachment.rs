//! Read only the immutable version bound to this dispatch. Bytes live in memory until upload.
use crate::Error;
use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use yuki_plugin_sdk::Id;

const PAGE: usize = 16_384;
const LIMIT: usize = 16 * 1024 * 1024;

pub fn part(arguments: &Value) -> Result<Value, Error> {
    let message = &arguments["message"];
    let media = &arguments["media"];
    let fields = message.as_object().ok_or("missing message")?;
    if fields.keys().any(|k| {
        !matches!(
            k.as_str(),
            "artifact_id" | "attachment_kind" | "name" | "text"
        )
    }) || media["artifact_id"].as_str().is_none()
        || media["artifact_id"] != message["artifact_id"]
        || media["version"]
            .as_str()
            .is_none_or(|v| v.len() != 64 || !v.bytes().all(|c| c.is_ascii_hexdigit()))
        || !matches!(message["attachment_kind"].as_str(), Some("image" | "file"))
    {
        return Err("unsupported attachment".into());
    }
    let name = message["name"]
        .as_str()
        .ok_or("missing selected filename")?;
    // The multipart filename is data, never a local path or curl form directive.
    if name.is_empty()
        || name.len() > 255
        || name == "."
        || name == ".."
        || name
            .chars()
            .any(|c| c.is_control() || matches!(c, '/' | '\\' | '"' | ';' | ','))
    {
        return Err("invalid attachment name".into());
    }
    let mut part = json!({"media":media,"kind":message["attachment_kind"],"name":name});
    if let Some(text) = message.get("text") {
        let text = text.as_str().ok_or("invalid attachment caption")?;
        if text.chars().count() > 1024 {
            return Err("attachment caption exceeds one part".into());
        }
        if !text.is_empty() {
            part["caption"] = json!(text);
        }
    }
    Ok(part)
}

pub struct Read {
    pub dispatch: Id,
    pub arguments: Value,
    pub handle: String,
    data: Vec<u8>,
    total: Option<usize>,
    mime: Option<String>,
}

impl Read {
    pub fn new(dispatch: Id, params: Value) -> Result<Self, Error> {
        let args = &params["arguments"];
        if args["purpose"] != "deliver"
            || args["part_ordinal"].as_u64().is_none()
            || args["media"].is_null()
            || args["part"]["media"] != args["media"]
        {
            return Err("media dispatch mismatch".into());
        }
        let handle = params["handle"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("missing bound handle")?
            .to_owned();
        Ok(Self {
            dispatch,
            arguments: args.clone(),
            handle,
            data: Vec::new(),
            total: None,
            mime: None,
        })
    }

    pub fn next(&self) -> Value {
        json!({"handle":self.handle,"offset":self.data.len(),"length":PAGE})
    }

    pub fn request_id(&self) -> Id {
        Id::Text(format!("media:{}:{}", self.handle, self.data.len()))
    }

    pub fn receive(&mut self, page: Value) -> Result<bool, Error> {
        let version = self.arguments["media"]["version"]
            .as_str()
            .ok_or("no version")?;
        let total = page["total"]
            .as_u64()
            .filter(|n| *n <= LIMIT as u64)
            .ok_or("invalid attachment length")? as usize;
        let mime = page["mime"]
            .as_str()
            .filter(|s| {
                s.len() <= 255
                    && s.split_once('/')
                        .is_some_and(|(a, b)| !a.is_empty() && !b.is_empty())
                    && s.bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"/+.-".contains(&b))
            })
            .ok_or("invalid attachment MIME")?;
        let chunk = STANDARD.decode(page["bytes"].as_str().ok_or("no attachment bytes")?)?;
        if page["offset"].as_u64() != Some(self.data.len() as u64)
            || page["version"] != version
            || self.total.is_some_and(|v| v != total)
            || self.mime.as_deref().is_some_and(|m| m != mime)
            || chunk.len() > PAGE
            || self.data.len() + chunk.len() > total
            || (chunk.is_empty() && total != 0)
        {
            return Err("inconsistent attachment page".into());
        }
        self.total = Some(total);
        self.mime = Some(mime.into());
        self.data.extend_from_slice(&chunk);
        let done = page["done"].as_bool().ok_or("missing attachment EOF")?;
        if done != (self.data.len() == total)
            || (done && format!("{:x}", Sha256::digest(&self.data)) != version)
        {
            return Err("attachment integrity failure".into());
        }
        Ok(done)
    }

    pub fn into_upload(self) -> Result<(Value, String, Vec<u8>), Error> {
        Ok((self.arguments, self.mime.ok_or("missing MIME")?, self.data))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reader(bytes: &[u8]) -> Read {
        Read::new(Id::Number(5), json!({"handle":"original","arguments":{
            "purpose":"deliver","part_ordinal":0,
            "media":{"artifact_id":"selected","version":format!("{:x}",Sha256::digest(bytes))},
            "part":{"media":{"artifact_id":"selected","version":format!("{:x}",Sha256::digest(bytes))}}
        }})).unwrap()
    }

    fn page(bytes: &[u8]) -> Value {
        json!({"total":bytes.len(),"mime":"application/octet-stream","offset":0,
            "version":format!("{:x}",Sha256::digest(bytes)),"bytes":STANDARD.encode(bytes),"done":true})
    }

    #[test]
    fn validates_bound_bytes_and_all_page_metadata_before_upload() {
        let bytes = b"original immutable bytes";
        let mut selected = reader(bytes);
        assert!(selected.receive(page(bytes)).unwrap());
        assert_eq!(selected.into_upload().unwrap().2, bytes);
        for (field, altered) in [
            ("version", json!("a".repeat(64))),
            ("offset", json!(1)),
            ("total", json!(LIMIT + 1)),
            ("done", json!(false)),
            ("bytes", json!(STANDARD.encode(b"other immutable bytes"))),
            ("mime", json!("text/plain\r\nInjected: yes")),
        ] {
            let mut changed = page(bytes);
            changed[field] = altered;
            assert!(reader(bytes).receive(changed).is_err(), "{field}");
        }
    }
}
