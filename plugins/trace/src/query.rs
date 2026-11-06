use serde_json::{Value, json};

/// Bound one caller-selected page. The Host owns every authority decision.
pub fn parameters(value: &Value) -> Result<Value, &'static str> {
    let object = value.as_object().ok_or("trace arguments must be an object")?;
    if object.keys().any(|k| !matches!(k.as_str(), "kind" | "identity" | "after" | "limit" | "content")) {
        return Err("unknown trace argument");
    }
    let kind = object.get("kind").and_then(Value::as_str).ok_or("kind is required")?;
    if !matches!(kind, "turn" | "work" | "event") { return Err("unsupported trace kind"); }
    let identity = object.get("identity").and_then(Value::as_str).ok_or("identity is required")?;
    if identity.is_empty() || identity.len() > 128 { return Err("invalid trace identity"); }
    let number = |key, default| match object.get(key) {
        None => Ok(default),
        Some(v) => v.as_u64().ok_or("trace cursor and limit must be unsigned integers"),
    };
    let after = number("after", 0)?;
    let limit = number("limit", 20)?;
    if !(1..=20).contains(&limit) { return Err("trace page limit must be between 1 and 20"); }
    let content = match object.get("content") {
        None => false,
        Some(Value::Bool(v)) => *v,
        Some(_) => return Err("content requires an explicit boolean"),
    };
    Ok(json!({"kind": kind, "identity": identity, "after": after, "limit": limit, "content": content}))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_requires_an_explicit_boolean() {
        let base = json!({"kind": "event", "identity": "1"});
        assert_eq!(parameters(&base).unwrap()["content"], false);
        for invalid in [json!("false"), json!(1), Value::Null] {
            let mut request = base.clone(); request["content"] = invalid;
            assert!(parameters(&request).is_err());
        }
        let mut explicit = base; explicit["content"] = json!(true);
        assert_eq!(parameters(&explicit).unwrap()["content"], true);
    }

    #[test]
    fn caller_fields_and_unbounded_pages_fail_before_dispatch() {
        for extra in [json!({"actor":"operator"}), json!({"handle":"another"}), json!({"limit":250}), json!({"after":-1})] {
            let mut request = json!({"kind":"event","identity":"1"});
            request.as_object_mut().unwrap().extend(extra.as_object().unwrap().clone());
            assert!(parameters(&request).is_err());
        }
    }
}
