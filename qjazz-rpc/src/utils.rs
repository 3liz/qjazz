use std::str::FromStr;
use tonic::metadata::{AsciiMetadataValue, KeyAndValueRef, MetadataKey, MetadataMap};
use tonic::Status;

// gRPC metadata utilities

// Convert gRPC metadata to qjazz headers format
pub(crate) fn metadata_to_headers(metadata: &MetadataMap) -> Vec<(&str, &str)> {
    metadata
        .iter()
        .filter_map(|key_value| match key_value {
            KeyAndValueRef::Ascii(key, value) => value.to_str().map(|v| (key.as_str(), v)).ok(),
            _ => None,
        })
        .collect()
}

// Convert qjazz headers format to gRPC metadata
pub(crate) fn headers_to_metadata(
    metadata: &mut MetadataMap,
    status: i64,
    headers: &[(String, String)],
) {
    metadata.insert("x-reply-status-code", status.into());
    for (k, v) in headers.iter() {
        if let Ok(v) = AsciiMetadataValue::from_str(v) {
            if let Ok(k) = MetadataKey::from_str(k) {
                metadata.insert(k, v);
            } else {
                log::error!("Invalid response header key {:?}", k);
            }
        } else {
            log::error!("Invalid response header value {:?}", v);
        }
    }
}
