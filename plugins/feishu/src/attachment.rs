//! Read the original selected version before one native upload, retaining no private files.
use crate::{Config, Error, transport::Body};
use data_encoding::BASE64;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::io::Write;
use yuki_plugin_sdk::Id;

const PAGE: usize = 16_384;
const LIMIT: usize = 16 * 1024 * 1024;

fn filename(value: &Value) -> Result<&str, Error> {
    value
        .as_str()
        .filter(|name| {
            !name.is_empty()
                && name.len() <= 4096
                && !matches!(*name, "." | "..")
                && !name
                    .chars()
                    .any(|c| c.is_control() || matches!(c, '/' | '\\'))
        })
        .ok_or_else(|| "invalid original attachment filename".into())
}

pub fn origin(cfg: &Config, namespace: &str, value: &Value) -> Result<(), Error> {
    if value["namespace"] != namespace
        || value["platform"] != cfg.domain
        || value["identity"] != json!({"application":cfg.app,"tenant":cfg.tenant})
        || ["stage", "deployment"]
            .iter()
            .any(|key| value[key].as_str().is_none_or(str::is_empty))
    {
        return Err("different original resource application".into());
    }
    Ok(())
}

pub fn preparation(args: &Value) -> Result<Value, Error> {
    let message = &args["message"];
    let media = &args["media"];
    if media["artifact_id"].as_str().is_none_or(str::is_empty)
        || media["artifact_id"] != message["artifact_id"]
        || media["version"]
            .as_str()
            .is_none_or(|v| v.len() != 64 || !v.bytes().all(|b| b.is_ascii_hexdigit()))
        || !matches!(message["attachment_kind"].as_str(), Some("image" | "file"))
    {
        return Err("invalid selected attachment".into());
    }
    Ok(
        json!({"preparation":true,"kind":message["attachment_kind"],"name":filename(&message["name"])?,"media":media}),
    )
}

pub fn message(args: &Value) -> Result<Value, Error> {
    let part = args["part"].as_object().ok_or("missing prepared part")?;
    let prepared = &args["prepared"];
    if part
        .keys()
        .any(|k| !matches!(k.as_str(), "prepared_part" | "kind" | "reply"))
        || part["prepared_part"]
            .as_u64()
            .zip(args["part_ordinal"].as_u64())
            .is_none_or(|(prior, current)| prior >= current)
        || prepared["operation"].as_str().is_none_or(str::is_empty)
        || prepared["media"] != args["media"]
        || args["media"]["artifact_id"]
            .as_str()
            .is_none_or(str::is_empty)
        || args["media"]["version"]
            .as_str()
            .is_none_or(|v| v.len() != 64 || !v.bytes().all(|b| b.is_ascii_hexdigit()))
        || prepared["resource"]["kind"] != part["kind"]
        || args["purpose"] != "deliver"
    {
        return Err("prepared resource does not match original attachment".into());
    }
    let key = crate::segments::native(&prepared["resource"]["key"])?;
    let content = match part["kind"].as_str() {
        Some("image") => json!({"image_key":key}),
        Some("file") => json!({"file_key":key}),
        _ => return Err("unsupported prepared attachment kind".into()),
    };
    Ok(json!({"msg_type":part["kind"],"content":content.to_string()}))
}

pub fn multipart(args: &Value, mime: &str, bytes: Vec<u8>) -> Result<Body, Error> {
    let part = &args["part"];
    let name = filename(&part["name"])?;
    let image = match part["kind"].as_str() {
        Some("image") => true,
        Some("file") => false,
        _ => return Err("unsupported attachment kind".into()),
    };
    if bytes.is_empty()
        || bytes.len() > LIMIT
        || mime.len() > 255
        || !mime.contains('/')
        || !mime.bytes().all(|b| (0x20..=0x7e).contains(&b))
    {
        return Err("invalid selected attachment bytes or MIME".into());
    }
    let boundary = format!("yuki-{:x}", Sha256::digest(&bytes));
    if bytes
        .windows(boundary.len())
        .any(|v| v == boundary.as_bytes())
        || name.contains(&boundary)
        || mime.contains(&boundary)
    {
        return Err("multipart boundary occurs in original attachment".into());
    }
    let mut body = Vec::new();
    if image {
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"image_type\"\r\n\r\nmessage\r\n"
        )?;
    } else {
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file_type\"\r\n\r\nstream\r\n"
        )?;
        write!(
            body,
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file_name\"\r\n\r\n{name}\r\n"
        )?;
    }
    let field = if image { "image" } else { "file" };
    let quoted_name = name.replace('"', "\\\"");
    write!(
        body,
        "--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{quoted_name}\"\r\nContent-Type: {mime}\r\n\r\n"
    )?;
    body.extend_from_slice(&bytes);
    write!(body, "\r\n--{boundary}--\r\n")?;
    Ok(Body {
        content_type: format!("multipart/form-data; boundary={boundary}"),
        bytes: body,
    })
}

pub struct Read {
    pub original_id: Id,
    pub page_id: Option<Id>,
    args: Value,
    handle: String,
    bytes: Vec<u8>,
    total: Option<usize>,
    mime: Option<String>,
    complete: bool,
}

impl Read {
    pub fn new(
        cfg: &Config,
        namespace: &str,
        original_id: Id,
        params: Value,
    ) -> Result<Self, Error> {
        let args = &params["arguments"];
        origin(cfg, namespace, &args["preparation_origin"])?;
        if args["purpose"] != "deliver"
            || args["part_ordinal"].as_u64().is_none()
            || args["part"]["preparation"] != true
            || args["part"].as_object().is_none_or(|part| {
                part.keys()
                    .any(|key| !matches!(key.as_str(), "preparation" | "kind" | "name" | "media"))
            })
            || args["part"]["media"] != args["media"]
            || args["media"]["artifact_id"]
                .as_str()
                .is_none_or(str::is_empty)
            || args["media"]["version"]
                .as_str()
                .is_none_or(|v| v.len() != 64 || !v.bytes().all(|c| c.is_ascii_hexdigit()))
            || !matches!(args["part"]["kind"].as_str(), Some("image" | "file"))
            || args.get("reply").is_some()
            || args["part"].get("reply").is_some()
        {
            return Err("original preparation mismatch".into());
        }
        filename(&args["part"]["name"])?;
        let handle = params["handle"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("missing original media handle")?
            .to_owned();
        Ok(Self {
            original_id,
            page_id: None,
            args: args.clone(),
            handle,
            bytes: Vec::new(),
            total: None,
            mime: None,
            complete: false,
        })
    }

    pub fn page(&self) -> Value {
        json!({"handle":self.handle,"offset":self.bytes.len(),"length":PAGE})
    }

    pub fn accept(&mut self, page: &Value) -> Result<bool, Error> {
        let total = page["total"]
            .as_u64()
            .filter(|n| (1..=LIMIT as u64).contains(n))
            .ok_or("invalid original media size")? as usize;
        let mime = page["mime"]
            .as_str()
            .filter(|s| {
                s.len() <= 255 && s.contains('/') && s.bytes().all(|b| (0x20..=0x7e).contains(&b))
            })
            .ok_or("invalid original media MIME")?;
        let encoded = page["bytes"]
            .as_str()
            .filter(|s| s.len() <= PAGE.div_ceil(3) * 4)
            .ok_or("invalid media page")?;
        let bytes = BASE64.decode(encoded.as_bytes())?;
        if self.complete
            || page["offset"].as_u64() != Some(self.bytes.len() as u64)
            || page["version"] != self.args["media"]["version"]
            || self.total.is_some_and(|value| value != total)
            || self.mime.as_deref().is_some_and(|value| value != mime)
            || bytes.is_empty()
            || bytes.len() > PAGE
            || self.bytes.len() + bytes.len() > total
        {
            return Err("changed original media page".into());
        }
        self.total = Some(total);
        self.mime = Some(mime.to_owned());
        self.bytes.extend_from_slice(&bytes);
        let done = self.bytes.len() == total;
        if page["done"].as_bool() != Some(done)
            || (done
                && self.args["media"]["version"] != format!("{:x}", Sha256::digest(&self.bytes)))
        {
            return Err("incomplete original media".into());
        }
        self.complete = done;
        Ok(done)
    }

    pub fn finish(self) -> Result<(Value, String, Vec<u8>), Error> {
        if !self.complete {
            return Err("original media is incomplete".into());
        }
        Ok((
            self.args,
            self.mime.ok_or("missing original media MIME")?,
            self.bytes,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn cfg() -> Config {
        Config {
            app: "app".into(),
            tenant: "tenant".into(),
            domain: "feishu".into(),
            secret: "fixture".into(),
            base: url::Url::parse("http://127.0.0.1").unwrap(),
            proxy: None,
        }
    }
    fn params(bytes: &[u8]) -> Value {
        let media = json!({"artifact_id":"original-version","version":format!("{:x}", Sha256::digest(bytes))});
        json!({"handle":"selected","arguments":{"purpose":"deliver","part_ordinal":0,
            "media":media,"part":{"preparation":true,"kind":"file","name":"原始\"雪.bin","media":media},
            "preparation_origin":{"namespace":"original","platform":"feishu","stage":"stage","deployment":"deployment",
                "identity":{"application":"app","tenant":"tenant"}}}})
    }
    fn page(bytes: &[u8]) -> Value {
        json!({"offset":0,"total":bytes.len(),"mime":"application/octet-stream",
            "bytes":BASE64.encode(bytes),"version":format!("{:x}",Sha256::digest(bytes)),"done":true})
    }
    #[test]
    fn original_pages_require_all_metadata_and_full_digest() {
        let bytes = b"original\0\r\nbytes";
        for field in ["offset", "total", "mime", "bytes", "version", "done"] {
            let mut reader = Read::new(&cfg(), "original", Id::Number(2), params(bytes)).unwrap();
            let mut invalid = page(bytes);
            invalid[field] = Value::Null;
            assert!(reader.accept(&invalid).is_err(), "{field}");
        }
        let mut reader = Read::new(&cfg(), "original", Id::Number(2), params(bytes)).unwrap();
        let mut changed = page(bytes);
        changed["bytes"] = json!(BASE64.encode(b"different bytes!"));
        assert!(reader.accept(&changed).is_err());
        let mut reader = Read::new(&cfg(), "original", Id::Number(2), params(bytes)).unwrap();
        assert!(reader.accept(&page(bytes)).unwrap());
        assert!(reader.accept(&page(bytes)).is_err());
        assert_eq!(reader.finish().unwrap().2, bytes);
        assert!(Read::new(&cfg(), "another", Id::Number(2), params(bytes)).is_err());
        assert!(
            Read::new(&cfg(), "original", Id::Number(2), params(bytes))
                .unwrap()
                .finish()
                .is_err()
        );
    }
    #[test]
    fn multipart_preserves_bytes_and_escapes_original_name() {
        let bytes = b"original\0\r\nbytes";
        let args = &params(bytes)["arguments"];
        let body = multipart(args, "application/octet-stream", bytes.to_vec()).unwrap();
        assert!(body.bytes.windows(bytes.len()).any(|part| part == bytes));
        let text = String::from_utf8_lossy(&body.bytes);
        assert!(text.contains("filename=\"原始\\\"雪.bin\""));
        assert!(text.contains("name=\"file_type\"\r\n\r\nstream"));
        assert!(multipart(args, "application/octet-stream\r\nX: value", bytes.to_vec()).is_err());
        assert!(multipart(args, "application/octet-stream", Vec::new()).is_err());
        for name in ["../x", "x\\y", "x\r\ny", "", ".."] {
            let mut args = args.clone();
            args["part"]["name"] = json!(name);
            assert!(multipart(&args, "application/octet-stream", bytes.to_vec()).is_err());
        }
    }

    #[test]
    fn visible_resource_requires_the_original_preparation() {
        let media = params(b"bytes")["arguments"]["media"].clone();
        let args = json!({"part":{"prepared_part":0,"kind":"file"},"part_ordinal":2,
            "purpose":"deliver","media":media,"prepared":{"operation":"original-upload",
                "media":media,"resource":{"kind":"file","key":"original-key"}}});
        assert_eq!(
            message(&args).unwrap(),
            json!({"msg_type":"file","content":"{\"file_key\":\"original-key\"}"})
        );
        for field in ["media", "operation", "resource"] {
            let mut changed = args.clone();
            changed["prepared"][field] = Value::Null;
            assert!(message(&changed).is_err());
        }
        let mut changed = args.clone();
        changed["part_ordinal"] = json!(0);
        assert!(message(&changed).is_err());
        let mut changed = args;
        changed["part"]["kind"] = json!("image");
        assert!(message(&changed).is_err());
    }
}
