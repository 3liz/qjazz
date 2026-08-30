//! Utils

use serde_json::{Map, Value};

use crate::errors::{Error, Result};

/// Patch provided JSON document (given as `serde_json::Value`) in place with JSON Merge Patch
/// (RFC 7396).
///
/// From https://github.com/idubrov/json-patch/blob/main/src/lib.rs
///
pub fn json_merge(doc: &mut Value, patch: &Value) -> Result<()> {
    json_merge_1(doc, patch, 0)
}

// Bound recursion: avoid nesting depth configuration
const MAX_DEPTH: usize = 32;

fn json_merge_1(doc: &mut Value, patch: &Value, depth: usize) -> Result<()> {
    if depth > MAX_DEPTH {
        return Err(Error::InvalidConfigValue("Recursion limit reached".into()));
    }

    if !patch.is_object() {
        *doc = patch.clone();
        return Ok(());
    }

    if !doc.is_object() {
        *doc = Value::Object(Map::new());
    }
    let map = doc.as_object_mut().unwrap();
    for (key, value) in patch.as_object().unwrap() {
        if value.is_null() {
            map.remove(key.as_str());
        } else {
            json_merge_1(
                map.entry(key.as_str()).or_insert(Value::Null),
                value,
                depth + 1,
            )?;
        }
    }
    Ok(())
}
