use std::str::FromStr;
use tonic::metadata::{AsciiMetadataValue, KeyAndValueRef, MetadataKey, MetadataMap};

// gRPC metadata utilities

// Convert gRPC metadata to qjazz headers format
pub(crate) fn metadata_to_headers(metadata: &MetadataMap) -> Vec<(&str, &str)> {
    metadata
        .iter()
        .filter_map(|key_value| match key_value {
            // Filter tonic transport headers
            KeyAndValueRef::Ascii(key, value) => match key.as_str() {
                "content-type"|"te"|"user-agent" => None,
                key if key.starts_with("grpc-") => None,
                key => value.to_str().map(|v| (key, v)).ok(),
            },
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
        let (Ok(k), Ok(v)) = (MetadataKey::from_str(k), AsciiMetadataValue::from_str(v)) else {
            log::error!("Invalid response header {k:?} {v:?}");
            continue;
        };
        metadata.insert(k, v);
    }
}
