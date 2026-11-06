//! Wire4 metadata codec. Capabilities describe native instances, never authority.
use serde_json::{Value, json};
use std::collections::BTreeSet;

pub struct Snapshot { pub capabilities: Value, pub instances: Vec<Value> }
pub fn snapshot(frame: &Value, device: &str, hello: bool) -> Result<Snapshot, &'static str> {
    if hello {
        if frame["type"] != "hello" || frame["protocol_version"] != 4 || !frame["instances"].is_array() {
            return Err("unsupported_connector_protocol");
        }
        if frame.get("device_id").is_some_and(|v| v != device) { return Err("external_agent_device_mismatch"); }
    } else if frame["type"] != "catalog" { return Err("invalid_connector_message"); }
    let items = frame["instances"].as_array().ok_or("invalid_connector_catalog")?;
    if items.len() > 4096 { return Err("connector_catalog_limit"); }
    let mut ids = BTreeSet::new();
    let mut instances = Vec::new();
    for item in items {
        let id = item["id"].as_str().filter(|s| !s.is_empty() && s.len() <= 1024).ok_or("invalid_connector_catalog")?;
        if !ids.insert(id) { return Err("invalid_connector_catalog"); }
        let mut stored = json!({"id":id});
        for key in ["label", "driver", "capabilities", "status", "error_type"] {
            if let Some(value) = item.get(key) { stored[key] = value.clone(); }
        }
        instances.push(stored);
    }
    let capabilities = frame.get("device_capabilities").cloned().unwrap_or(json!({}));
    if !capabilities.is_object() { return Err("invalid_connector_catalog"); }
    Ok(Snapshot { capabilities, instances })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn authority_fields_cannot_replace_original_device_or_instance_keys() {
        let value = json!({"type":"hello","protocol_version":4,"device_id":"original",
            "person_id":"forged","instances":[{"id":"same","label":"native","person_id":"forged"}]});
        let parsed = snapshot(&value, "original", true).unwrap();
        assert_eq!(parsed.instances, [json!({"id":"same","label":"native"})]);
        assert!(snapshot(&value, "other", true).is_err());
        assert!(snapshot(&json!({"type":"hello","protocol_version":5,"instances":[]}), "original", true).is_err());
        assert!(snapshot(&json!({"type":"catalog","instances":[{"id":"same"},{"id":"same"}]}), "original", false).is_err());
    }
}
