//! Read only the original plan or dispatch selection through bounded Host pages.
use crate::{Config, Error, segments};
use data_encoding::BASE64;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use yuki_plugin_sdk::Id;

pub struct Reading {
    pub original_id: Id,
    pub page_id: Option<Id>,
    pub planning: bool,
    params: Value,
    size: usize,
    digest: String,
    bytes: Vec<u8>,
}

impl Reading {
    pub fn new(original_id: Id, params: Value, planning: bool) -> Result<Self, Error> {
        let descriptor = if planning {
            &params["arguments"]["text_source"]
        } else {
            &params["arguments"]["part"]["text_range"]
        };
        let size = descriptor[if planning { "bytes" } else { "length" }]
            .as_u64()
            .filter(|size| (1..=8 * 1024 * 1024).contains(size))
            .ok_or("invalid original text size")? as usize;
        let digest = descriptor["sha256"]
            .as_str()
            .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
            .ok_or("invalid original text digest")?
            .to_owned();
        if params["handle"].as_str().is_none_or(str::is_empty)
            || (planning && params["arguments"]["message"].get("text").is_some())
            || (!planning && params["arguments"]["part"].get("text").is_some())
        {
            return Err("ambiguous original text selection".into());
        }
        Ok(Self {
            original_id,
            page_id: None,
            planning,
            params,
            size,
            digest,
            bytes: Vec::new(),
        })
    }

    pub fn page(&self) -> Value {
        json!({"handle":self.params["handle"],"offset":self.bytes.len(),"length":12288})
    }

    pub fn accept(&mut self, page: &Value) -> Result<bool, Error> {
        if page["offset"].as_u64() != Some(self.bytes.len() as u64)
            || page["total"].as_u64() != Some(self.size as u64)
            || page["sha256"] != self.digest
        {
            return Err("changed original text page".into());
        }
        let encoded = page["bytes"]
            .as_str()
            .filter(|s| s.len() <= 16384)
            .ok_or("invalid text page bytes")?;
        let bytes = BASE64.decode(encoded.as_bytes())?;
        if bytes.is_empty() || bytes.len() > 12288 || bytes.len() > self.size - self.bytes.len() {
            return Err("text page outside original selection".into());
        }
        self.bytes.extend(bytes);
        let done = self.bytes.len() == self.size;
        if page["done"].as_bool() != Some(done)
            || (done && format!("{:x}", Sha256::digest(&self.bytes)) != self.digest)
        {
            return Err("incomplete original text".into());
        }
        Ok(done)
    }

    pub fn finish(mut self, cfg: &Config) -> Result<Value, Error> {
        if self.bytes.len() != self.size {
            return Err("original text is incomplete".into());
        }
        let text = String::from_utf8(self.bytes)?;
        let args = &mut self.params["arguments"];
        if self.planning {
            args["message"]["text"] = json!(text);
            let mut plan = segments::plan(cfg, args)?;
            let mut start = 0;
            for part in plan["parts"].as_array_mut().ok_or("missing text plan")? {
                let Some(text) = part["text"].as_str() else {
                    continue;
                };
                let length = text.len();
                let digest = format!("{:x}", Sha256::digest(text.as_bytes()));
                part.as_object_mut()
                    .ok_or("invalid text part")?
                    .remove("text");
                part["text_range"] = json!({"start":start,"length":length,"sha256":digest});
                start += length;
            }
            Ok(plan)
        } else {
            args["part"]
                .as_object_mut()
                .ok_or("missing text part")?
                .remove("text_range");
            args["part"]["text"] = json!(text);
            Ok(args.take())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_page_digest_offset_and_completion_are_required() {
        let bytes = "雪".as_bytes();
        let digest = format!("{:x}", Sha256::digest(bytes));
        let params = json!({"handle":"original","arguments":{"message":{},
            "text_source":{"bytes":bytes.len(),"sha256":digest}}});
        let valid = json!({"offset":0,"total":3,"sha256":digest,
            "bytes":BASE64.encode(bytes),"done":true});
        for field in ["offset", "total", "sha256", "bytes", "done"] {
            let mut reader = Reading::new(Id::Number(1), params.clone(), true).unwrap();
            let mut page = valid.clone();
            page[field] = Value::Null;
            assert!(reader.accept(&page).is_err(), "{field}");
        }
        let mut reader = Reading::new(Id::Number(1), params, true).unwrap();
        assert!(reader.accept(&valid).unwrap());
    }
}
