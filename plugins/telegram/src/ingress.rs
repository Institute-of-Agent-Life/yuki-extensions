use serde_json::{Value, json};

fn integer(v: &Value, key: &str) -> Result<i64, &'static str> {
    v[key].as_i64().ok_or("missing Telegram integer")
}

fn text_segments(raw: &Value, bot: i64, username: &str) -> Result<Vec<Value>, &'static str> {
    let (text, entities) = if let Some(text) = raw["text"].as_str() {
        (text, &raw["entities"])
    } else {
        (
            raw["caption"].as_str().unwrap_or(""),
            &raw["caption_entities"],
        )
    };
    let mut mentions: Vec<_> = entities
        .as_array()
        .into_iter()
        .flatten()
        .filter(|e| matches!(e["type"].as_str(), Some("mention" | "text_mention")))
        .collect();
    mentions.sort_by_key(|e| e["offset"].as_u64());
    let utf16: Vec<u16> = text.encode_utf16().collect();
    let mut segments = Vec::new();
    let mut cursor = 0;
    let slice = |low, high| -> Result<String, &'static str> {
        String::from_utf16(utf16.get(low..high).ok_or("invalid entity range")?)
            .map_err(|_| "entity splits a UTF-16 scalar")
    };
    for entity in mentions {
        let start = usize::try_from(integer(entity, "offset")?).map_err(|_| "negative offset")?;
        let length = usize::try_from(integer(entity, "length")?).map_err(|_| "negative length")?;
        let end = start.checked_add(length).ok_or("entity overflow")?;
        if start < cursor || length == 0 {
            return Err("overlapping or empty mention");
        }
        if start > cursor {
            segments.push(json!({"type":"text","text":slice(cursor,start)?}));
        }
        let token = slice(start, end)?;
        let user = &entity["user"];
        let id = user["id"].as_i64();
        let own = id == Some(bot)
            || (entity["type"] == "mention"
                && !username.is_empty()
                && token.trim_start_matches('@').eq_ignore_ascii_case(username));
        let mut mention = json!({"type":"mention","label":token,"span":{"segment":segments.len(),
            "start":slice(0,start)?.chars().count(),"end":slice(0,end)?.chars().count()}});
        if let Some(native) = if own { Some(bot) } else { id } {
            mention["native"] = native.to_string().into();
        }
        segments.push(mention);
        cursor = end;
    }
    if cursor < utf16.len() {
        segments.push(json!({"type":"text","text":slice(cursor,utf16.len())?}));
    }
    Ok(segments)
}

fn content(raw: &Value, bot: i64, username: &str) -> Result<Vec<Value>, &'static str> {
    let mut segments = text_segments(raw, bot, username)?;
    for (field, base_kind) in [
        ("photo", "image"),
        ("animation", "video"),
        ("video", "video"),
        ("voice", "audio"),
        ("audio", "audio"),
        ("document", "file"),
        ("video_note", "video"),
        ("sticker", "image"),
    ] {
        if field == "document" && raw["animation"].is_object() {
            continue;
        }
        let file = if field == "photo" {
            raw[field].as_array().and_then(|v| v.last())
        } else {
            raw.get(field)
        };
        let Some(file) = file.filter(|f| f["file_id"].is_string()) else {
            continue;
        };
        let kind = match field {
            "sticker" if file["is_video"] == true => "video",
            "sticker" if file["is_animated"] == true => "file",
            _ => base_kind,
        };
        segments.push(json!({"type":"media","kind":kind,"reference":file["file_id"]}));
    }
    Ok(segments)
}

pub fn normalize(update: &Value, bot: i64, username: &str) -> Result<Value, &'static str> {
    let revision = integer(update, "update_id")?;
    let edited = update["edited_message"].is_object();
    let raw = if edited {
        &update["edited_message"]
    } else {
        &update["message"]
    };
    let chat = integer(&raw["chat"], "id")?;
    let mid = integer(raw, "message_id")?;
    let author = raw
        .get("from")
        .filter(|a| a["id"].is_i64())
        .unwrap_or(&raw["sender_chat"]);
    let sender = integer(author, "id")?.to_string();
    let mut segments = content(raw, bot, username)?;
    let body = !segments.is_empty();
    if let Some(reply) = raw.get("reply_to_message") {
        let reply_chat = reply["chat"]["id"].as_i64().unwrap_or(chat);
        let reply_id = integer(reply, "message_id")?;
        segments.push(json!({"type":"reply","native_id":format!("{reply_chat}:{reply_id}")}));
    }
    let migration = raw
        .get("migrate_to_chat_id")
        .or(raw.get("migrate_from_chat_id"));
    if migration.is_some() {
        let previous = raw["migrate_from_chat_id"].as_i64().unwrap_or(chat);
        let current = raw["migrate_to_chat_id"].as_i64().unwrap_or(chat);
        segments.push(json!({"type":"text","text":format!("Telegram chat migration: {previous} -> {current}")}));
    }
    if let Some(title) = raw["new_chat_title"].as_str() {
        segments.push(json!({"type":"text","text":title}));
    }
    let ordinary = body && !edited && migration.is_none() && author["is_bot"] != true;
    let kind = if migration.is_some() || !body {
        "data"
    } else if edited {
        "edit"
    } else if author["is_bot"] == true {
        "echo"
    } else {
        "message"
    };
    let occurred = raw["edit_date"]
        .as_i64()
        .or(raw["date"].as_i64())
        .map(|seconds| {
            seconds
                .checked_mul(1000)
                .ok_or("Telegram timestamp overflow")
        })
        .transpose()?;
    Ok(
        json!({"source":format!("{chat}:{mid}"),"native_id":format!("{chat}:{mid}"),"sender":sender,
        "space":(raw["chat"]["type"] != "private").then(||chat.to_string()),"topic":raw["message_thread_id"].as_i64().map(|v|v.to_string()),
        "native_version":edited.then(||revision.to_string()),"kind":kind,"segments":segments,
        "occurred":occurred,"accept":ordinary}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn utf16_caption_tracks_native_mentions_after_an_astral_scalar() {
        let raw = json!({"caption":"🌨 @YukiBot!", "caption_entities":[
            {"type":"mention","offset":3,"length":8}]});
        let result = text_segments(&raw, 101, "yukibot").unwrap();
        assert_eq!(result[0]["text"], "🌨 ");
        assert_eq!(result[1]["native"], "101");
        assert_eq!(result[2]["text"], "!");
        let bad = json!({"text":"🌨","entities":[{"type":"mention","offset":1,"length":1}]});
        assert!(text_segments(&bad, 101, "YukiBot").is_err());
    }

    #[test]
    fn edit_and_migration_do_not_request_main_admission() {
        let envelope = json!({"message_id":8,"chat":{"id":-21},"from":{"id":9},"text":"update"});
        let edit = normalize(
            &json!({"update_id":71,"edited_message":envelope}),
            101,
            "bot",
        )
        .unwrap();
        assert_eq!(edit["accept"], false);
        assert_eq!(edit["native_version"], "71");
        let mut migrated = envelope;
        migrated["migrate_from_chat_id"] = (-6).into();
        let data = normalize(&json!({"update_id":72,"message":migrated}), 101, "bot").unwrap();
        assert_eq!(data["kind"], "data");
        assert_eq!(
            data["segments"][1]["text"],
            "Telegram chat migration: -6 -> -21"
        );
    }
}
