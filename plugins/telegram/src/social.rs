//! Original plain-text Telegram delivery. The Host owns each operation and its retry policy.
use crate::{Error, transport};
use serde_json::{Value, json};
use yuki_plugin_sdk::Id;

const TEXT_LIMIT: usize = 4096;

fn route(arguments: &Value, bot: i64) -> Result<(&str, Option<i64>), Error> {
    let route = &arguments["route"];
    if route["bot"].as_str() != Some(bot.to_string().as_str()) {
        return Err("wrong original Telegram bot".into());
    }
    let chat = route["chat"].as_str().ok_or("missing original chat")?;
    if chat.parse::<i64>()?.to_string() != chat || chat == "0" {
        return Err("invalid Telegram chat".into());
    }
    let topic = match route.get("topic") {
        None | Some(Value::Null) => None,
        Some(v) => {
            let value = v.as_str().ok_or("invalid topic")?;
            let parsed: i64 = value.parse()?;
            if parsed <= 0 || parsed.to_string() != value {
                return Err("invalid Telegram topic".into());
            }
            Some(parsed)
        }
    };
    Ok((chat, topic))
}

fn plain_text(value: &Value) -> Result<&str, Error> {
    let fields = value.as_object().ok_or("missing Telegram message")?;
    if fields.len() != 1 {
        return Err("unsupported Telegram message fields".into());
    }
    fields
        .get("text")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| "missing text".into())
}

pub fn plan(arguments: &Value, bot: i64) -> Result<Value, Error> {
    route(arguments, bot)?;
    let message = &arguments["message"];
    if !arguments["media"].is_null() {
        let text = match message.get("text") {
            None => "",
            Some(text) => text.as_str().ok_or("invalid attachment caption")?,
        };
        let end = text
            .char_indices()
            .nth(1024)
            .map_or(text.len(), |(byte, _)| byte);
        let mut first = arguments.clone();
        first["message"]["text"] = json!(&text[..end]);
        let mut parts = vec![crate::attachment::part(&first)?];
        if end < text.len() {
            let tail = plan(
                &json!({"route":arguments["route"],"message":{"text":&text[end..]}}),
                bot,
            )?;
            parts.extend(
                tail["parts"]
                    .as_array()
                    .ok_or("invalid text plan")?
                    .iter()
                    .cloned(),
            );
        }
        return Ok(json!({"parts":parts}));
    }
    let text = plain_text(message)?;
    let mut start = 0;
    let mut parts = Vec::new();
    for (index, (byte, _)) in text.char_indices().enumerate().skip(1) {
        if index % TEXT_LIMIT == 0 {
            parts.push(json!({"text":&text[start..byte]}));
            start = byte;
        }
    }
    parts.push(json!({"text":&text[start..]}));
    Ok(json!({"parts":parts}))
}

pub struct Pending {
    pub id: Id,
    chat: String,
    transfer: transport::Request,
}

impl Pending {
    pub fn start(
        id: Id,
        arguments: &Value,
        bot: i64,
        base: &str,
        token: &str,
    ) -> Result<Self, Value> {
        let failed = || json!({"state":"failed"});
        let (chat, topic) = route(arguments, bot).map_err(|_| failed())?;
        let text = plain_text(&arguments["part"]).map_err(|_| failed())?;
        if text.chars().count() > TEXT_LIMIT || arguments["part_ordinal"].as_u64().is_none() {
            return Err(failed());
        }
        // Plain text has no parse_mode. Telegram displays the original literal characters.
        let mut payload = json!({"chat_id":chat, "text":text});
        if let Some(topic) = topic {
            payload["message_thread_id"] = topic.into();
        }
        let url = format!("{base}/bot{token}/sendMessage");
        let transfer = transport::start(&url, Some(&payload), 128 * 1024)
            .map_err(|_| json!({"state":"unknown"}))?;
        Ok(Self {
            id,
            chat: chat.into(),
            transfer,
        })
    }

    pub fn upload(
        id: Id,
        args: &Value,
        bot: i64,
        base: &str,
        mime: &str,
        bytes: Vec<u8>,
    ) -> Result<Self, Error> {
        let (chat, topic) = route(args, bot)?;
        let part = &args["part"];
        // Validate again at dispatch before passing any name to the native API.
        let mut message = json!({"artifact_id":args["media"]["artifact_id"],"attachment_kind":part["kind"],"name":part["name"]});
        if let Some(caption) = part.get("caption") {
            message["text"] = caption.clone();
        }
        let checked = crate::attachment::part(&json!({"media":args["media"],"message":message}))?;
        if checked != *part {
            return Err("attachment part changed".into());
        }
        let (method, field) = match (part["kind"].as_str(), mime) {
            (Some("file"), _) => ("sendDocument", "document"),
            (Some("image"), "image/gif") => ("sendAnimation", "animation"),
            (Some("image"), m) if m.starts_with("image/") => ("sendPhoto", "photo"),
            _ => return Err("unsupported attachment type".into()),
        };
        let transfer = transport::upload(
            base,
            method,
            field,
            chat,
            topic,
            part["name"].as_str().ok_or("missing name")?,
            mime,
            part["caption"].as_str(),
            bytes,
        )?;
        Ok(Self {
            id,
            chat: chat.into(),
            transfer,
        })
    }

    pub fn ready(&mut self) -> bool {
        self.transfer.ready().unwrap_or(true)
    }

    pub fn finish(self) -> Value {
        let Ok((status, bytes)) = self.transfer.response() else {
            return json!({"state":"unknown"});
        };
        let Ok(response) = serde_json::from_slice::<Value>(&bytes) else {
            return json!({"state":"unknown"});
        };
        if (400..500).contains(&status)
            && response["ok"] == false
            && response["error_code"].as_u64() == Some(u64::from(status))
        {
            return json!({"state":"failed"});
        }
        let message = &response["result"];
        if status == 200
            && response["ok"] == true
            && message["chat"]["id"]
                .as_i64()
                .is_some_and(|id| id.to_string() == self.chat)
            && let Some(id) = message["message_id"].as_i64().filter(|v| *v > 0)
        {
            return json!({"state":"confirmed","locator":format!("{}:{id}",self.chat)});
        }
        json!({"state":"unknown"})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preserves_caption_then_text_with_one_immutable_attachment() {
        let text = format!("{}🌨{}", "雪".repeat(1023), "a".repeat(4097));
        let media = json!({"artifact_id":"selected","version":"a".repeat(64)});
        let request = json!({"route":{"bot":"101","chat":"-15","topic":"7"},
            "message":{"artifact_id":"selected","attachment_kind":"file","name":"source.bin","text":text},"media":media});
        let parts = plan(&request, 101).unwrap();
        let parts = parts["parts"].as_array().unwrap();
        assert_eq!(parts.len(), 3);
        assert_eq!(parts[0]["media"], media);
        assert_eq!(parts[0]["caption"].as_str().unwrap().chars().count(), 1024);
        assert_eq!(parts[1]["text"].as_str().unwrap().len(), 4096);
        assert_eq!(parts[2]["text"], "a");
        assert!(parts[1..].iter().all(|part| part.get("media").is_none()));
        let joined = format!(
            "{}{}{}",
            parts[0]["caption"].as_str().unwrap(),
            parts[1]["text"].as_str().unwrap(),
            parts[2]["text"].as_str().unwrap()
        );
        assert_eq!(joined, text);
        assert!(plan(&request, 102).is_err());
    }
    #[test]
    fn preserves_unicode_and_rejects_unsupported_parts_before_dispatch() {
        let text = format!("{}🌨&", "雪".repeat(4095));
        let mut a = json!({"route":{"bot":"101","chat":"-15","topic":"7"},"message":{"text":text}});
        let parts = plan(&a, 101).unwrap();
        assert_eq!(
            parts["parts"][0]["text"].as_str().unwrap().chars().count(),
            4096
        );
        assert_eq!(parts["parts"][1]["text"], "&");
        assert!(plan(&a, 102).is_err());
        a["message"]["reply_to_event_id"] = 7.into();
        assert!(plan(&a, 101).is_err());
    }
}
