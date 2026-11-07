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
// A numbered placeholder ends after its last digit. An unlisted @_user_100
// must stay text even when this event supplies a binding for @_user_1.
fn key_position(input: &str, key: &str) -> Option<usize> {
    let numbered = key
        .strip_prefix("@_user_")
        .is_some_and(|suffix| !suffix.is_empty() && suffix.bytes().all(|b| b.is_ascii_digit()));
    input.match_indices(key).find_map(|(pos, _)| {
        let next = input.as_bytes().get(pos + key.len());
        (!numbered || !next.is_some_and(u8::is_ascii_digit)).then_some(pos)
    })
}

fn inline(segments: &mut Vec<Value>, mut input: &str, mentions: &[Value]) {
    while !input.is_empty() {
        let hit = mentions
            .iter()
            .filter_map(|m| {
                let key = m["key"].as_str().filter(|k| !k.is_empty())?;
                Some((
                    key_position(input, key)?,
                    key,
                    m["id"]["open_id"].as_str().filter(|id| !id.is_empty())?,
                    m["name"]
                        .as_str()
                        .filter(|s| !s.is_empty())
                        .unwrap_or("未识别成员"),
                ))
            })
            .min_by_key(|(pos, key, ..)| (*pos, std::cmp::Reverse(key.len())));
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
    if let Some(key) = reference.as_str().filter(|s| !s.is_empty()) {
        segments.push(json!({"type":"media","kind":kind,"reference":key}));
    }
}

fn post_segments(
    segments: &mut Vec<Value>,
    content: &Value,
    mentions: &[Value],
) -> Result<(), Error> {
    let body = if content["content"].is_array() {
        content
    } else {
        content
            .get("zh_cn")
            .or_else(|| content.get("en_us"))
            .or_else(|| {
                content
                    .as_object()?
                    .values()
                    .find(|value| value.is_object())
            })
            .ok_or("empty post")?
    };
    if let Some(title) = body["title"].as_str().filter(|s| !s.is_empty()) {
        text(segments, &format!("{title}\n"));
    }
    let rows = body["content"].as_array().ok_or("invalid post")?;
    for (index, row) in rows.iter().enumerate() {
        if index > 0 {
            text(segments, "\n");
        }
        for item in row.as_array().ok_or("invalid post row")? {
            match item["tag"].as_str() {
                Some("text" | "md" | "code_block") => {
                    inline(segments, item["text"].as_str().unwrap_or(""), mentions)
                }
                Some("a") => {
                    let label = item["text"].as_str().unwrap_or("");
                    let href = item["href"].as_str().unwrap_or("");
                    if label.is_empty() {
                        text(segments, href);
                    } else if href.is_empty() || href == label {
                        text(segments, label);
                    } else {
                        text(segments, &format!("{label} ({href})"));
                    }
                }
                Some("at") => {
                    if let Some(id) = item["user_id"].as_str().filter(|s| !s.is_empty()) {
                        let name = item["user_name"]
                            .as_str()
                            .filter(|s| !s.is_empty())
                            .or_else(|| {
                                mentions.iter().find(|m| m["id"]["open_id"] == id)?["name"]
                                    .as_str()
                                    .filter(|s| !s.is_empty())
                            })
                            .unwrap_or("未识别成员");
                        mention(segments, id, name);
                    }
                }
                Some("emotion") => {
                    if let Some(name) = item["emoji_type"].as_str().filter(|s| !s.is_empty()) {
                        text(segments, &format!("[{name}]"));
                    }
                }
                Some("img") => media(segments, "image", &item["image_key"]),
                Some("media") => media(segments, "video", &item["file_key"]),
                _ => {}
            }
        }
    }
    Ok(())
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
    // The reply endpoint accepts a message ID. Preserve the original root
    // message as the route, matching the v4 ingress contract.
    let thread = raw
        .get("thread_id")
        .filter(|v| !v.is_null())
        .map(|v| v.as_str().ok_or("invalid native thread"))
        .transpose()?
        .filter(|thread| !thread.is_empty());
    let topic_root = if thread.is_some() {
        Some(
            raw.get("root_id")
                .filter(|v| !v.is_null())
                .map(|v| v.as_str().ok_or("invalid original thread root"))
                .transpose()?
                .filter(|root| !root.is_empty())
                .unwrap_or(id),
        )
    } else {
        None
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
        Some("file") => media(&mut segments, "file", &content["file_key"]),
        Some("sticker") => text(&mut segments, "[原生贴纸]"),
        Some("audio") => media(&mut segments, "audio", &content["file_key"]),
        Some("media") => media(&mut segments, "video", &content["file_key"]),
        Some("post") => post_segments(&mut segments, content, mentions)?,
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
    let mut result = json!({"source":id,"native_id":id,"sender":sender,"space":group,"topic":thread,
        "occurred":time,"kind":kind,"segments":segments,"accept":human});
    if let Some(root) = topic_root {
        result["topic_root"] = json!(root);
    }
    Ok(Some(result))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thread_routes_preserve_the_original_root_message() {
        let mut body = json!({"header":{"app_id":"cli_a","tenant_key":"tenant-a","event_type":"im.message.receive_v1"},
            "event":{"sender":{"sender_type":"user","sender_id":{"open_id":"ou_user"}},
            "message":{"message_id":"om_current","chat_id":"oc_group","chat_type":"group",
                "thread_id":"omt_native","root_id":"om_root","message_type":"text","content":{"text":"hello"}}}});
        let route = normalize(&body, "cli_a", "tenant-a").unwrap().unwrap();
        assert_eq!(route["topic"], "omt_native");
        assert_eq!(route["topic_root"], "om_root");
        assert_eq!(route["native_id"], "om_current");
        body["event"]["message"]["root_id"] = Value::Null;
        assert_eq!(
            normalize(&body, "cli_a", "tenant-a").unwrap().unwrap()["topic_root"],
            "om_current"
        );
        body["event"]["message"]["root_id"] = json!(7);
        assert!(normalize(&body, "cli_a", "tenant-a").is_err());
        body["event"]["message"]["root_id"] = Value::Null;
        body["event"]["message"]["thread_id"] = json!(7);
        assert!(normalize(&body, "cli_a", "tenant-a").is_err());
        body["event"]["message"]["thread_id"] = Value::Null;
        assert!(normalize(&body, "cli_a", "tenant-a").unwrap().unwrap()["topic"].is_null());
    }

    #[test]
    fn text_mentions_bind_the_complete_original_key() {
        let short = json!({"key":"@_user_1","id":{"open_id":"short"},"name":"One"});
        let long = json!({"key":"@_user_10","id":{"open_id":"long"},"name":"Ten"});
        for mentions in [[short.clone(), long.clone()], [long, short]] {
            let mut segments = Vec::new();
            inline(
                &mut segments,
                "未列 @_user_100；@_user_10@_user_1",
                &mentions,
            );
            assert_eq!(
                segments,
                vec![
                    json!({"type":"text","text":"未列 @_user_100；"}),
                    json!({"type":"mention","native":"long","label":"@Ten"}),
                    json!({"type":"mention","native":"short","label":"@One"}),
                ]
            );
        }
    }

    #[test]
    fn opaque_keys_use_the_longest_binding_and_require_an_open_id() {
        let mut segments = Vec::new();
        inline(
            &mut segments,
            "@x+ @x @z",
            &[
                json!({"key":"@x","id":{"open_id":"short"}}),
                json!({"key":"@z","id":{"open_id":""}}),
                json!({"key":"@x+","id":{"open_id":"long"}}),
            ],
        );
        assert_eq!(
            segments,
            vec![
                json!({"type":"mention","native":"long","label":"@未识别成员"}),
                json!({"type":"text","text":" "}),
                json!({"type":"mention","native":"short","label":"@未识别成员"}),
                json!({"type":"text","text":" @z"}),
            ]
        );
    }
    #[test]
    fn post_labels_do_not_replace_original_targets_or_duplicate_link_text() {
        let body = json!({"content":[[
            {"tag":"at","user_id":"original","user_name":"from post"},
            {"tag":"at","user_id":"unknown"},
            {"tag":"a","href":"bare"}, {"tag":"a","href":"same","text":"same"},
            {"tag":"img","image_key":""}
        ]]});
        let mentions = [json!({"id":{"open_id":"original"},"name":"from table"})];
        let mut segments = Vec::new();
        post_segments(&mut segments, &body, &mentions).unwrap();
        assert_eq!(
            segments,
            vec![
                json!({"type":"mention","native":"original","label":"@from post"}),
                json!({"type":"mention","native":"unknown","label":"@未识别成员"}),
                json!({"type":"text","text":"bare"}),
                json!({"type":"text","text":"same"}),
            ]
        );
    }
}
