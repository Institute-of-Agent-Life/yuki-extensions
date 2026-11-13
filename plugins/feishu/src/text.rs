//! Read the original text and account annotations through the same dispatched Host handle.
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
    annotations: bool,
    complete: bool,
}
impl Reading {
    pub fn new(original_id: Id, params: Value, planning: bool) -> Result<Self, Error> {
        if params["handle"].as_str().is_none_or(str::is_empty)
            || params["arguments"].get("mentions").is_some()
        {
            return Err("ambiguous original content selection".into());
        }
        let has_text = if planning {
            params["arguments"].get("text_source").is_some()
        } else {
            params["arguments"]["part"].get("text_range").is_some()
        };
        let mut reading = Self {
            original_id,
            page_id: None,
            planning,
            params,
            size: 0,
            digest: String::new(),
            bytes: Vec::new(),
            annotations: !has_text,
            complete: false,
        };
        reading.select(!has_text)?;
        Ok(reading)
    }
    fn select(&mut self, annotations: bool) -> Result<(), Error> {
        let args = &self.params["arguments"];
        let descriptor = if annotations {
            &args["mentions_source"]
        } else if self.planning {
            &args["text_source"]
        } else {
            &args["part"]["text_range"]
        };
        let maximum = if annotations {
            128 * 1024 * 1024
        } else {
            8 * 1024 * 1024
        };
        let size = descriptor[if annotations || self.planning {
            "bytes"
        } else {
            "length"
        }]
        .as_u64()
        .filter(|size| (1..=maximum).contains(size))
        .ok_or("invalid original content size")? as usize;
        let digest = descriptor["sha256"]
            .as_str()
            .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
            .ok_or("invalid original content digest")?
            .to_owned();
        if !annotations
            && (if self.planning {
                args["message"].get("text").is_some()
            } else {
                args["part"].get("text").is_some()
            })
        {
            return Err("ambiguous original text selection".into());
        }
        self.annotations = annotations;
        self.size = size;
        self.digest = digest;
        self.bytes.clear();
        Ok(())
    }
    pub fn method(&self) -> &'static str {
        if self.annotations {
            "gateway.read_mentions"
        } else {
            "gateway.read_text"
        }
    }
    pub fn page(&self) -> Value {
        json!({"handle":self.params["handle"],"offset":self.bytes.len(),"length":12288})
    }
    pub fn accept(&mut self, page: &Value) -> Result<bool, Error> {
        if self.complete
            || page["offset"].as_u64() != Some(self.bytes.len() as u64)
            || page["total"].as_u64() != Some(self.size as u64)
            || page["sha256"] != self.digest
        {
            return Err("changed original content page".into());
        }
        let encoded = page["bytes"]
            .as_str()
            .filter(|s| s.len() <= 16384)
            .ok_or("invalid content page bytes")?;
        let bytes = BASE64.decode(encoded.as_bytes())?;
        if bytes.is_empty() || bytes.len() > 12288 || bytes.len() > self.size - self.bytes.len() {
            return Err("content page outside original selection".into());
        }
        self.bytes.extend(bytes);
        let done = self.bytes.len() == self.size;
        if page["done"].as_bool() != Some(done)
            || (done && format!("{:x}", Sha256::digest(&self.bytes)) != self.digest)
        {
            return Err("incomplete original content".into());
        }
        if !done {
            return Ok(false);
        }
        let args = &mut self.params["arguments"];
        if self.annotations {
            let value: Value = serde_json::from_slice(&self.bytes)?;
            if !value.is_array() {
                return Err("annotations must be an original array".into());
            }
            args["mentions"] = value;
            args.as_object_mut()
                .ok_or("missing arguments")?
                .remove("mentions_source");
        } else {
            let text = String::from_utf8(std::mem::take(&mut self.bytes))?;
            if self.planning {
                args["message"]["text"] = json!(text);
                args.as_object_mut()
                    .ok_or("missing arguments")?
                    .remove("text_source");
            } else {
                args["part"]
                    .as_object_mut()
                    .ok_or("missing part")?
                    .remove("text_range");
                args["part"]["text"] = json!(text);
            }
            if args.get("mentions_source").is_some() {
                self.select(true)?;
                return Ok(false);
            }
        }
        self.complete = true;
        self.bytes.clear();
        Ok(true)
    }
    pub fn finish(mut self, cfg: &Config) -> Result<Value, Error> {
        if !self.complete {
            return Err("original content is incomplete".into());
        }
        let args = &mut self.params["arguments"];
        if !self.planning {
            return Ok(args.take());
        }
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
