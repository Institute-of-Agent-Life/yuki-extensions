//! Preserve the original native recipient, quote and v4 text byte limit.
use crate::{Config, Error, attachment, mentions};
use serde_json::{Value, json};
use url::Url;

const TEXT_BYTES: usize = 150_000;

pub fn native(value: &Value) -> Result<&str, Error> {
    value
        .as_str()
        .filter(|v| {
            !v.is_empty()
                && v.len() <= 4096
                && !matches!(*v, "." | "..")
                && !v.chars().any(char::is_control)
        })
        .ok_or_else(|| "invalid original native ID".into())
}

fn route<'a>(cfg: &Config, args: &'a Value) -> Result<(&'a str, &'a str, Option<&'a str>), Error> {
    let route = &args["route"];
    if route["bot"] != cfg.app {
        return Err("wrong original application".into());
    }
    let scope = route["scope"]
        .as_str()
        .filter(|s| matches!(*s, "private" | "group"))
        .ok_or("missing original scope")?;
    let chat = native(&route["chat"])?;
    let root = if route["topic"].is_null() {
        None
    } else {
        native(&route["topic"])?;
        if scope != "group" {
            return Err("private thread is unsupported".into());
        }
        Some(native(&route["topic_root"])?)
    };
    Ok((chat, scope, root))
}

fn reply(args: &Value) -> Result<Option<&str>, Error> {
    let Some(value) = args.get("reply") else {
        return Ok(None);
    };
    if value.as_object().is_none_or(|v| v.len() != 2)
        || value["event_id"].as_i64().is_none_or(|id| id <= 0)
    {
        return Err("invalid original reply".into());
    }
    Ok(Some(native(&value["native_id"])?))
}

fn text_body(text: &str) -> Value {
    json!({"msg_type":"text", "content":json!({"text":text}).to_string()})
}

pub fn plan(cfg: &Config, args: &Value) -> Result<Value, Error> {
    route(cfg, args)?;
    reply(args)?;
    if args["message"]
        .get("reply_to_event_id")
        .filter(|v| !v.is_null())
        != args.get("reply").map(|r| &r["event_id"])
    {
        return Err("original quote mismatch".into());
    }
    let message = args["message"].as_object().ok_or("missing message")?;
    if message.keys().any(|k| {
        !matches!(
            k.as_str(),
            "text" | "target" | "reply_to_event_id" | "artifact_id" | "attachment_kind" | "name"
        )
    }) {
        return Err("unsupported original message".into());
    }
    let mut parts = Vec::new();
    if !args["media"].is_null() {
        parts.push(attachment::preparation(args)?);
    } else if ["artifact_id", "attachment_kind", "name"]
        .iter()
        .any(|k| message.contains_key(*k))
    {
        return Err("missing selected attachment".into());
    }
    let text = match message.get("text") {
        Some(value) => value.as_str().ok_or("invalid text")?,
        None => "",
    };
    if text.is_empty() && parts.is_empty() {
        return Err("missing text or selected attachment".into());
    }
    let annotations = mentions::read(args, text)?;
    let first_visible = parts.len();
    let mut remaining = annotations.iter().peekable();
    let boundaries: Vec<_> = text
        .char_indices()
        .filter_map(|(index, _)| {
            while remaining.peek().is_some_and(|mention| mention.end <= index) {
                remaining.next();
            }
            if remaining
                .peek()
                .is_some_and(|mention| mention.start < index && index < mention.end)
            {
                None
            } else {
                Some(index)
            }
        })
        .chain(std::iter::once(text.len()))
        .collect();
    let mut start = 0;
    while start + 1 < boundaries.len() {
        let mut low = start + 1;
        let mut high = boundaries.len() - 1;
        while low <= high {
            let end = low + (high - low) / 2;
            if text_body(&mentions::render(
                text,
                &annotations,
                boundaries[start],
                boundaries[end],
            )?)
            .to_string()
            .len()
                <= TEXT_BYTES
            {
                low = end + 1;
            } else {
                high = end - 1;
            }
        }
        if high <= start {
            return Err("text exceeds native limit".into());
        }
        parts.push(json!({"text":&text[boundaries[start]..boundaries[high]]}));
        start = high;
    }
    if first_visible == 1 {
        parts.push(json!({"prepared_part":0,"kind":message["attachment_kind"]}));
    }
    if let Some(reply) = args.get("reply") {
        parts[first_visible]["reply"] = reply.clone();
    }
    if parts.len() > 64 {
        return Err("original native plan exceeds part limit".into());
    }
    Ok(json!({"parts":parts}))
}

pub fn delivery(cfg: &Config, args: &Value) -> Result<(Url, Value), Error> {
    let (chat, scope, root) = route(cfg, args)?;
    let quote = reply(args)?;
    if args.get("reply") != args["part"].get("reply") || args["part_ordinal"].as_u64().is_none() {
        return Err("original part quote mismatch".into());
    }
    let part = args["part"].as_object().ok_or("missing native part")?;
    let mut body = if part.contains_key("prepared_part") {
        attachment::message(args)?
    } else {
        if part.keys().any(|k| !matches!(k.as_str(), "text" | "reply"))
            || args.get("prepared").is_some()
        {
            return Err("unsupported native part".into());
        }
        let text = part
            .get("text")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .ok_or("missing text")?;
        let annotations = mentions::read(args, text)?;
        let body = text_body(&mentions::render(text, &annotations, 0, text.len())?);
        if body.to_string().len() > TEXT_BYTES {
            return Err("native text limit exceeded".into());
        }
        body
    };
    let mut url = cfg.base.join("open-apis/im/v1/messages")?;
    if let Some(parent) = quote.or(root) {
        url.path_segments_mut()
            .map_err(|_| "invalid regional endpoint")?
            .push(parent)
            .push("reply");
        body["reply_in_thread"] = json!(root.is_some());
    } else {
        body["receive_id"] = json!(chat);
        url.query_pairs_mut().append_pair(
            "receive_id_type",
            if scope == "private" {
                "open_id"
            } else {
                "chat_id"
            },
        );
    }
    Ok((url, body))
}

pub fn recall(cfg: &Config, args: &Value) -> Result<Url, Error> {
    route(cfg, args)?;
    let original = &args["original"];
    if original["event_id"].as_i64().is_none_or(|id| id <= 0)
        || ["execution", "operation"]
            .iter()
            .any(|k| original[k].as_str().is_none_or(str::is_empty))
    {
        return Err("missing original recall identity".into());
    }
    let mut url = cfg.base.join("open-apis/im/v1/messages")?;
    url.path_segments_mut()
        .map_err(|_| "invalid regional endpoint")?
        .push(native(&original["native_id"])?);
    Ok(url)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config() -> Config {
        Config {
            app: "cli_original".into(),
            secret: "fixture".into(),
            tenant: "tenant".into(),
            domain: "feishu".into(),
            base: Url::parse("http://127.0.0.1:8080").unwrap(),
            proxy: None,
        }
    }
    fn args() -> Value {
        json!({"route":{"bot":"cli_original","scope":"group","chat":"oc_original","topic":"thread","topic_root":"om_root"},"message":{"text":"你好"}})
    }
    #[test]
    fn unicode_and_json_escaping_keep_the_original_text() {
        let mut args = args();
        let text = "🌨\n\"\\雪".repeat(30_000);
        args["message"]["text"] = json!(text);
        let plan = plan(&config(), &args).unwrap();
        let parts = plan["parts"].as_array().unwrap();
        assert!(parts.len() >= 3);
        assert_eq!(
            parts
                .iter()
                .map(|p| p["text"].as_str().unwrap())
                .collect::<String>(),
            text
        );
        for part in parts {
            assert!(text_body(part["text"].as_str().unwrap()).to_string().len() <= TEXT_BYTES);
        }
    }
    #[test]
    fn quote_precedes_topic_and_recipient_type_comes_from_scope() {
        let mut args = args();
        let quote = json!({"event_id":4,"native_id":"om_quote/#?"});
        args["message"]["reply_to_event_id"] = json!(4);
        args["reply"] = quote.clone();
        args["part"] = plan(&config(), &args).unwrap()["parts"][0].clone();
        args["part_ordinal"] = json!(0);
        let (url, body) = delivery(&config(), &args).unwrap();
        assert!(url.as_str().ends_with("/om_quote%2F%23%3F/reply"));
        assert_eq!(body["reply_in_thread"], true);
        args.as_object_mut().unwrap().remove("reply");
        args["part"].as_object_mut().unwrap().remove("reply");
        assert!(
            delivery(&config(), &args)
                .unwrap()
                .0
                .as_str()
                .ends_with("/om_root/reply")
        );
        args["route"]["topic"] = Value::Null;
        args["route"]["scope"] = json!("private");
        args["route"]["chat"] = json!("opaque-without-a-prefix");
        assert_eq!(
            delivery(&config(), &args).unwrap().0.query(),
            Some("receive_id_type=open_id")
        );
        args["route"]["bot"] = json!("another-app");
        assert!(delivery(&config(), &args).is_err());
    }
    #[test]
    fn upload_precedes_caption_and_only_first_visible_part_quotes() {
        let mut args = args();
        let quote = json!({"event_id":4,"native_id":"om_quote"});
        args["media"] = json!({"artifact_id":"original","version":"a".repeat(64)});
        args["message"]["artifact_id"] = json!("original");
        args["message"]["attachment_kind"] = json!("file");
        args["message"]["name"] = json!("原始.bin");
        args["message"]["reply_to_event_id"] = json!(4);
        args["reply"] = quote.clone();
        let planned = plan(&config(), &args).unwrap();
        let parts = planned["parts"].as_array().unwrap();
        assert_eq!(parts.len(), 3);
        assert_eq!(parts[0]["preparation"], true);
        assert_eq!(parts[0]["media"], args["media"]);
        assert_eq!(parts[1]["text"], "你好");
        assert_eq!(parts[1]["reply"], quote);
        assert!(parts[0].get("reply").is_none() && parts[2].get("reply").is_none());
        assert_eq!(parts[2], json!({"prepared_part":0,"kind":"file"}));
        args["message"].as_object_mut().unwrap().remove("text");
        let planned = plan(&config(), &args).unwrap();
        assert_eq!(planned["parts"].as_array().unwrap().len(), 2);
        assert_eq!(planned["parts"][1]["reply"], quote);
    }
    #[test]
    fn original_native_content_and_boundaries_match_fixed_v4() {
        use sha2::{Digest, Sha256};
        let oracle: Value =
            serde_json::from_str(include_str!("../tests/v4-native-content.json")).unwrap();
        assert_eq!(
            oracle["baseline"],
            "329ca7c487414d2f54ddd98ff4727446ed2446cd"
        );
        for case in oracle["cases"].as_array().unwrap() {
            let text = case["unit"]
                .as_str()
                .unwrap()
                .repeat(case["repeat"].as_u64().unwrap() as usize);
            let marker = case["marker"].as_str().unwrap();
            let annotations: Vec<_> = text
                .match_indices(marker)
                .map(|(start, _)| {
                    json!({
                        "start": start,
                        "end": start + marker.len(),
                        "account": "original",
                        "native": case["native"],
                        "label": "小雪",
                        "assignment": "stage",
                        "source": 1
                    })
                })
                .collect();
            let mut args = args();
            args["message"]["text"] = json!(text);
            args["mentions"] = json!(annotations);
            let planned = plan(&config(), &args).unwrap();
            let parts = planned["parts"].as_array().unwrap();
            assert_eq!(
                parts.len(),
                case["parts"].as_array().unwrap().len(),
                "{}",
                case["name"]
            );
            let mut start = 0;
            for (index, (part, expected)) in parts
                .iter()
                .zip(case["parts"].as_array().unwrap())
                .enumerate()
            {
                let text = part["text"].as_str().unwrap();
                let end = start + text.len();
                args["mentions"] = json!(
                    annotations
                        .iter()
                        .filter(|m| m["start"].as_u64().unwrap() as usize >= start
                            && (m["end"].as_u64().unwrap() as usize) <= end)
                        .map(|m| {
                            let mut local = m.clone();
                            local["start"] = json!(m["start"].as_u64().unwrap() as usize - start);
                            local["end"] = json!(m["end"].as_u64().unwrap() as usize - start);
                            local
                        })
                        .collect::<Vec<_>>()
                );
                args["part"] = part.clone();
                args["part_ordinal"] = json!(index);
                let (_, body) = delivery(&config(), &args).unwrap();
                assert_eq!(
                    text.len(),
                    expected["text_bytes"].as_u64().unwrap() as usize
                );
                assert_eq!(
                    format!("{:x}", Sha256::digest(text.as_bytes())),
                    expected["text_sha256"]
                );
                assert_eq!(
                    format!(
                        "{:x}",
                        Sha256::digest(body["content"].as_str().unwrap().as_bytes())
                    ),
                    expected["content_sha256"]
                );
                start = end;
            }
        }
    }
}
