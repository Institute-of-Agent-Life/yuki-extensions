use serde_json::{Value, json};

pub fn request(arguments: &Value, handle: &Value) -> Result<(&'static str, Value), &'static str> {
    let input = arguments.as_object().ok_or("character arguments must be an object")?;
    if input.keys().any(|key| !matches!(key.as_str(), "action" | "body")) {
        return Err("unknown character argument");
    }
    let action = input.get("action").and_then(Value::as_str).ok_or("action is required")?;
    let (method, write) = match action {
        "public" => ("character.public", false),
        "identity" => ("character.identity", false),
        "read" => ("character.get", false),
        "soul" => ("character.soul.read", false),
        "update" => ("character.update", true),
        "save_soul" => ("character.soul.save", true),
        "reload_soul" => ("character.soul.reload", true),
        _ => return Err("unsupported character action"),
    };
    if write {
        let body = input.get("body").filter(|v| v.is_object()).ok_or("write body is required")?;
        // Preserve caller-selected request_id and expected_revision byte values.
        // The Host validates the fixed DTO, original caller and replay semantics.
        Ok(("control.write", json!({"handle":handle,"method":method,"body":body})))
    } else {
        if input.get("body").is_some_and(|v| v.as_object().is_none_or(|o| !o.is_empty())) {
            return Err("read action does not accept a write body");
        }
        Ok(("control.read", json!({"handle":handle,"method":method,"args":{}})))
    }
}
