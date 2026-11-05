use crate::rpc::{Rpc, Result};
use crate::worker::field;
use serde_json::{Value, json};
use std::{collections::BTreeMap, sync::atomic::AtomicBool};

// The core owns names, visibility and the frozen revision. Never derive script
// aliases from canonical names. Schemas are discarded after obtaining that alias;
// lookup_tools remains the core's on-demand schema API inside the script.
pub fn projection(rpc: &Rpc, handle: &str, cancel: &AtomicBool) -> Result<Value> {
    let mut offset = 0;
    let mut names = BTreeMap::new();
    loop {
        let page = rpc.call("tool.catalog", json!({"handle":handle,"offset":offset,"limit":10}), cancel)?;
        let items = page["items"].as_array().ok_or("catalog_invalid")?;
        for item in items {
            let name = field(item, "name")?;
            let schema = rpc.call("tool.schema", json!({"handle":handle,"name":name}), cancel)?;
            if schema["name"] != name { return Err("catalog_name_mismatch".into()); }
            // Null means the core explicitly excludes this capability from scripts.
            if schema["script_name"].is_null() { continue; }
            let script = field(&schema, "script_name")?;
            if names.insert(script.to_owned(), name.to_owned()).is_some() {
                return Err("catalog_duplicate_script_name".into());
            }
        }
        if page["next_offset"].is_null() { break; }
        let next = page["next_offset"].as_u64().ok_or("catalog_cursor_invalid")?;
        if next <= offset || names.len() > 4096 { return Err("catalog_limit".into()); }
        offset = next;
    }
    Ok(json!(names))
}
