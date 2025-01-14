//! Utils

use serde_json::{Map, Value};

/// Patch provided JSON document (given as `serde_json::Value`) in place with JSON Merge Patch
/// (RFC 7396).
///
/// From https://github.com/idubrov/json-patch/blob/main/src/lib.rs
///
pub fn json_merge(doc: &mut Value, patch: &Value) {
    if !patch.is_object() {
        *doc = patch.clone();
        return;
    }

    if !doc.is_object() {
        *doc = Value::Object(Map::new());
    }
    let map = doc.as_object_mut().unwrap();
    for (key, value) in patch.as_object().unwrap() {
        if value.is_null() {
            map.remove(key.as_str());
        } else {
            json_merge(map.entry(key.as_str()).or_insert(Value::Null), value);
        }
    }
}
