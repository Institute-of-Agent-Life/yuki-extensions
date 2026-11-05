use crate::Error;
use serde_json::{Value, json};

fn text(segments: &mut Vec<Value>, s: &str) {
    if !s.is_empty() {
        segments.push(json!({"type":"text","text":s}));
    }
}
fn mention(segments: &mut Vec<Value>, id: &str, name: &str) {
    segments.push(json!({"type":"mention","native":id,"label":format!("@{name}")}));
}
fn inline(segments: &mut Vec<Value>, mut input: &str, mentions: &[Value]) {
    while !input.is_empty() {
        let hit = mentions
            .iter()
            .filter_map(|m| {
                let key = m["key"].as_str().filter(|k| !k.is_empty())?;
                Some((
                    input.find(key)?,
                    key,
                    m["id"]["open_id"].as_str()?,
                    m["name"].as_str().unwrap_or(key),
                ))
            })
            .min_by_key(|(pos, ..)| *pos);
        let Some((pos, key, id, name)) = hit else {
            text(segments, input);
            break;
        };
        text(segments, &input[..pos]);
        mention(segments, id, name);
        input = &input[pos + key.len()..];
    }
}

fn media(segments: &mut Vec<Value>, kind: &str, reference: &Value) {
    if let Some(key) = reference.as_str() {
        segments.push(json!({"type":"media","kind":kind,"reference":key}));
    }
}

pub fn normalize(payload: &Value, app: &str, tenant: &str) -> Result<Option<Value>, Error> {
    let header = &payload["header"];
    if header["app_id"] != app || header["tenant_key"] != tenant {
        return Err("event scope mismatch".into());
    }
    if header["event_type"] != "im.message.receive_v1" {
        return Ok(None);
    }
    let event = &payload["event"];
    let raw = &event["message"];
    let sender = event["sender"]["sender_id"]["open_id"]
        .as_str()
        .ok_or("missing original open_id")?;
    let id = raw["message_id"].as_str().ok_or("missing message id")?;
    let chat = raw["chat_id"].as_str().ok_or("missing original chat")?;
    let group = match raw["chat_type"].as_str() {
        Some("group") => Some(chat),
        Some("p2p") => None,
        _ => return Err("unknown chat type".into()),
    };
    let parsed;
    let content = if let Some(encoded) = raw["content"].as_str() {
        parsed = serde_json::from_str::<Value>(encoded)?;
        &parsed
    } else {
        &raw["content"]
    };
    let mut segments = Vec::new();
    let mentions = raw["mentions"].as_array().map(Vec::as_slice).unwrap_or(&[]);
    match raw["message_type"].as_str() {
        Some("text") => inline(
            &mut segments,
            content["text"].as_str().ok_or("missing message text")?,
            mentions,
        ),
        Some("image") => media(&mut segments, "image", &content["image_key"]),
        Some("file" | "sticker") => media(&mut segments, "file", &content["file_key"]),
        Some("audio") => media(&mut segments, "audio", &content["file_key"]),
        Some("media") => media(&mut segments, "video", &content["file_key"]),
        Some("post") => {
            let body = if content["content"].is_array() {
                content
            } else {
                content
                    .get("zh_cn")
                    .or_else(|| content.get("en_us"))
                    .or_else(|| content.as_object()?.values().next())
                    .ok_or("empty post")?
            };
            if let Some(title) = body["title"].as_str() {
                text(&mut segments, title);
            }
            for row in body["content"].as_array().ok_or("invalid post")? {
                for item in row.as_array().ok_or("invalid post row")? {
                    match item["tag"].as_str() {
                        Some("text" | "a") => {
                            text(&mut segments, item["text"].as_str().unwrap_or(""))
                        }
                        Some("at") => {
                            if let Some(id) = item["user_id"].as_str() {
                                mention(
                                    &mut segments,
                                    id,
                                    item["user_name"].as_str().unwrap_or(id),
                                );
                            }
                        }
                        Some("img") => media(&mut segments, "image", &item["image_key"]),
                        Some("media") => media(&mut segments, "video", &item["file_key"]),
                        _ => {}
                    }
                }
            }
        }
        _ => {}
    }
    let human = !segments.is_empty() && event["sender"]["sender_type"] == "user";
    let kind = if segments.is_empty() {
        "data"
    } else if human {
        "message"
    } else {
        "echo"
    };
    if let Some(parent) = raw["parent_id"].as_str().filter(|id| !id.is_empty()) {
        segments.push(json!({"type":"reply","native_id":parent}));
    }
    let time = raw["create_time"]
        .as_str()
        .map(str::parse::<i64>)
        .transpose()?
        .or_else(|| raw["create_time"].as_i64());
    Ok(Some(
        json!({"source":id,"native_id":id,"sender":sender,"space":group,"topic":raw["thread_id"],
        "occurred":time,"kind":kind,"segments":segments,"accept":human}),
    ))
}
