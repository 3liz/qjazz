//
// Handle RPC responses
//
use actix_web::{
    error,
    http::{self, StatusCode},
    web, HttpResponse, HttpResponseBuilder,
};
use futures::stream::StreamExt;
use std::str::FromStr;
use tonic::{
    self,
    metadata::{KeyAndValueRef, MetadataKey, MetadataMap, MetadataValue},
};

use crate::channel::{qjazz_service::ResponseChunk, Channel};

struct AnyError;

impl<T> From<T> for AnyError
where
    T: std::error::Error,
{
    fn from(_: T) -> Self {
        Self
    }
}

pub mod metadata {
    use super::*;

    pub fn insert_header(md: &mut MetadataMap, key: &str, value: &str) -> Result<(), error::Error> {
        MetadataKey::from_str(key)
            .inspect_err(|e| log::error!("{e}"))
            .map_err(AnyError::from)
            .and_then(|k| {
                MetadataValue::from_str(value)
                    .inspect_err(|e| log::error!("{e}"))
                    .map_err(AnyError::from)
                    .map(|v| {
                        md.insert(k, v);
                    })
            })
            .map_err(|_| error::ErrorInternalServerError("Internal error"))
    }

    // Convert headers to metadata (infallible)
    pub fn insert_from_headers<F: FnMut(&str) -> bool>(
        md: &mut MetadataMap,
        headers: &http::header::HeaderMap,
        mut pred: F,
    ) {
        headers
            .iter()
            .filter(|(k, _)| pred(k.as_str()))
            .for_each(|(k, v)| {
                if let Ok(k) = MetadataKey::from_str(k.as_str()) {
                    if v.to_str()
                        .map_err(AnyError::from)
                        .and_then(|v| MetadataValue::from_str(v).map_err(AnyError::from))
                        .map(|v| md.insert(k, v))
                        .is_err()
                    {
                        log::error!("Invalid medatata value {:?}", v);
                    }
                } else {
                    log::error!("Failed to convert header key {:?}", k)
                }
            });
    }
}

//
// Wrap a Response builder
//

use std::ops::{Deref, DerefMut};

pub struct RpcHttpResponseBuilder {
    builder: HttpResponseBuilder,
    status_code: StatusCode,
}

impl Deref for RpcHttpResponseBuilder {
    type Target = HttpResponseBuilder;

    fn deref(&self) -> &Self::Target {
        &self.builder
    }
}

impl DerefMut for RpcHttpResponseBuilder {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.builder
    }
}

pub type ResponseStream = tonic::Response<tonic::codec::Streaming<ResponseChunk>>;

//
// Retreive bytes from streamed rpc response
//
pub async fn collect_payload(resp: ResponseStream) -> Result<Vec<u8>, tonic::Status> {
    let mut resp = resp.into_inner();
    Ok(if let Some(item) = resp.message().await? {
        let mut payload = item.chunk;
        while let Some(mut item) = resp.message().await? {
            payload.append(&mut item.chunk)
        }
        payload
    } else {
        Vec::default()
    })
}

impl RpcHttpResponseBuilder {
    pub fn status_code(&self) -> &StatusCode {
        &self.status_code
    }

    pub fn stream_bytes(
        mut self,
        resp: ResponseStream,
        channel: web::Data<Channel>,
    ) -> HttpResponse {
        self.builder
            .streaming(resp.into_inner().map(move |res| match res {
                Ok(item) => Ok(web::Bytes::from(item.chunk)),
                Err(status) => {
                    log::error!("Backend streaming error:\t{}\t{}", channel.name(), status);
                    Err(status)
                }
            }))
    }

    pub fn from_metadata(metadata: &MetadataMap, request_id: Option<String>) -> Self {
        Self::builder_from_metadata(StatusCode::OK, metadata, request_id)
    }
    //
    // Handle response status and headers
    //
    pub fn builder_from_metadata(
        code: StatusCode,
        metadata: &MetadataMap,
        request_id: Option<String>,
    ) -> Self {
        let mut status_code = code;
        let mut builder = HttpResponseBuilder::new(code);

        if let Some(id) = request_id {
            builder.insert_header(("x-request-id", id));
        }

        for (k, v) in metadata.iter().filter_map(|kv| match kv {
            KeyAndValueRef::Ascii(k, v) => k
                .as_str()
                .strip_prefix("x-reply-")
                .and_then(|k| v.to_str().map(|v| (k, v)).ok()),
            _ => None,
        }) {
            match k {
                "status-code" => {
                    status_code = StatusCode::from_u16(
                        v.parse()
                            .inspect_err(|e| {
                                log::error!("OWS: Invalid status code {:?}", e);
                            })
                            .unwrap_or(500u16),
                    )
                    .unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);
                    builder.status(status_code);
                }
                _ => {
                    if let Some(h) = k.strip_prefix("header-") {
                        builder.insert_header((h, v));
                    }
                }
            }
        }

        Self {
            builder,
            status_code,
        }
    }

    // Create http response builder
    // from gRPC status
    //
    // See https://grpc.io/docs/guides/status-codes/
    // for details about gRPC error codes.
    pub fn from_rpc_status(status: &tonic::Status, request_id: Option<String>) -> HttpResponse {
        let code = match status.code() {
            tonic::Code::DeadlineExceeded => StatusCode::GATEWAY_TIMEOUT,
            tonic::Code::PermissionDenied => StatusCode::FORBIDDEN,
            // XXX Cancelled is usually a response to an action from the caller.
            // Having this error here means that some external cause occured on
            // service side.
            tonic::Code::Cancelled => StatusCode::SERVICE_UNAVAILABLE,
            tonic::Code::Internal | tonic::Code::ResourceExhausted => {
                StatusCode::INTERNAL_SERVER_ERROR
            }
            tonic::Code::Unimplemented => StatusCode::NOT_IMPLEMENTED,
            tonic::Code::Unavailable => StatusCode::SERVICE_UNAVAILABLE,
            tonic::Code::Unauthenticated => StatusCode::UNAUTHORIZED,

            // User code generated errors
            // see https://grpc.io/docs/guides/status-codes
            //
            // Usually occurs when a non-Qgis error
            // is raised before reaching qgis server.
            code => {
                let code = match code {
                    tonic::Code::InvalidArgument => StatusCode::BAD_REQUEST,
                    tonic::Code::NotFound => StatusCode::NOT_FOUND,
                    tonic::Code::AlreadyExists => StatusCode::CONFLICT,
                    tonic::Code::FailedPrecondition => StatusCode::PRECONDITION_FAILED,
                    tonic::Code::Aborted => StatusCode::SERVICE_UNAVAILABLE,
                    // tonic::Code::OK
                    // tonic::Code::OutOfRange
                    // tonic::Code::Dataloss
                    // tonic::Code::Unknown

                    // Consider these errors as legitimate Ok responses
                    // or error which is out of gRPC namespace.
                    // In this case the error code may be  found in
                    // the metadata.
                    _ => StatusCode::OK,
                };

                return Self::builder_from_metadata(code, status.metadata(), request_id)
                    .content_type("text/plain")
                    .body(status.message().to_string());
            }
        };

        // Send informative message
        HttpResponseBuilder::new(code)
            .content_type("text/plain")
            .body(if code.is_server_error() {
                // Do not leak internal error messages
                code.canonical_reason()
                    .unwrap_or("Server error")
                    .to_string()
            } else {
                status.message().to_string()
            })
    }
}

// Handle response from RPC stream
pub enum StreamedResponse {
    Fail(HttpResponse),
    Succ(RpcHttpResponseBuilder, ResponseStream),
}

impl StreamedResponse {
    pub fn into_response(self, channel: web::Data<Channel>) -> HttpResponse {
        match self {
            Self::Fail(resp) => resp,
            Self::Succ(builder, resp) => builder.stream_bytes(resp, channel),
        }
    }

    // Stream response chunks
    pub fn new(
        response: std::result::Result<ResponseStream, tonic::Status>,
        name: &str,
        request_id: Option<String>,
    ) -> StreamedResponse {
        match response {
            Err(status) => {
                log::error!("Backend error:\t{}\t{}", name, status);
                StreamedResponse::Fail(RpcHttpResponseBuilder::from_rpc_status(&status, request_id))
            }
            Ok(resp) => StreamedResponse::Succ(
                RpcHttpResponseBuilder::from_metadata(resp.metadata(), request_id),
                resp,
            ),
        }
    }
}

//
// Attemps to extract the ows service exception XML
// message from the response data

pub fn service_exception_msg(msg: &str) -> Option<&str> {
    msg.split_once("<ServiceExceptionReport")
        .and_then(|(_, s)| s.split_once("<ServiceException"))
        .and_then(|(_, s)| s.split_once(">"))
        .and_then(|(_, s)| s.split_once("</ServiceException>"))
        .map(|(s, _)| s)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_service_exception_msg() {
        let msg = concat!(
            r#"<?xml version="1.0" encoding="UTF-8"?>\n"#,
            r#"<ServiceExceptionReport xmlns="http://www.opengis.net/ogc" version="1.3.0">\n "#,
            r#"<ServiceException code="InvalidParameterValue">"#,
            r#"The requested map size is too large"#,
            r#"</ServiceException>\n</ServiceExceptionReport>\n"#,
        );

        assert_eq!(
            service_exception_msg(msg),
            Some("The requested map size is too large")
        );
    }
}
