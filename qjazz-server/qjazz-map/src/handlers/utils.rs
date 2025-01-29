// Web utils

use actix_web::{
    http::{self, header::AsHeaderName, header::HeaderMap, StatusCode},
    web, HttpRequest, HttpResponse, HttpResponseBuilder,
};
use std::str::FromStr;
use tonic::{
    self,
    metadata::{KeyAndValueRef, MetadataKey, MetadataMap, MetadataValue},
};

pub mod request {

    #[derive(Default, Copy, Clone)]
    pub struct ProxyHeaders {
        pub allow: bool,
    }

    use super::*;

    /// Return a public url from Forwarded header informations
    /// as defined as defined in RFC 7239
    /// see https://docs.rs/actix-web/latest/actix_web/dev/struct.ConnectionInfo.html
    pub fn public_url(req: &HttpRequest, path: &str) -> String {
        if req
            .app_data::<web::ThinData<ProxyHeaders>>()
            .map(|data| data.0.allow)
            .unwrap_or(false)
        {
            let info = req.connection_info();

            let host = info.host();
            let proto = info.scheme();
            let prefix = req
                .headers()
                .get("x-forwarded-prefix")
                .map(|p| p.to_str().unwrap_or_default())
                .unwrap_or_default()
                .trim_end_matches('/');

            format!("{proto}://{host}{prefix}{path}")
        } else {
            format!("{}", req.uri())
        }
    }

    #[inline]
    pub fn location(req: &HttpRequest) -> String {
        public_url(req, req.path())
    }

    #[inline]
    pub fn header_as_str(req: &HttpRequest, key: impl AsHeaderName) -> Option<&str> {
        super::header::get_as_str(req.headers(), key)
    }

    #[inline]
    pub fn request_id(req: &HttpRequest) -> Option<&str> {
        super::header::request_id(req.headers())
    }
}

pub mod header {
    use super::*;

    /// Infaillible method that returns header as str
    pub fn get_as_str(headers: &HeaderMap, key: impl AsHeaderName) -> Option<&str> {
        headers.get(key).and_then(|v| v.to_str().ok())
    }

    #[inline]
    pub fn request_id(headers: &HeaderMap) -> Option<&str> {
        get_as_str(headers, "x-request-id")
    }
}

//
// Request builder factory
//

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

pub trait RpcResponseFactory {
    //
    // Handle response status and headers
    //
    fn from_metadata(metadata: &MetadataMap, request_id: Option<String>) -> HttpResponseBuilder {
        let mut builder = HttpResponseBuilder::new(StatusCode::OK);

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
                    builder.status(
                        StatusCode::from_u16(
                            v.parse()
                                .inspect_err(|e| {
                                    log::error!("OWS: Invalid status code {:?}", e);
                                })
                                .unwrap_or(500u16),
                        )
                        .unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
                    );
                }
                _ => {
                    if let Some(h) = k.strip_prefix("header-") {
                        builder.insert_header((h, v));
                    }
                }
            }
        }

        builder
    }

    // Create http response builder
    // from gRPC status
    //
    // See https://grpc.io/docs/guides/status-codes/
    // for details about gRPC error codes.
    fn from_rpc_status(status: &tonic::Status, request_id: Option<String>) -> HttpResponse {
        let code = match status.code() {
            tonic::Code::Ok => StatusCode::OK,
            tonic::Code::InvalidArgument => StatusCode::BAD_REQUEST,
            tonic::Code::DeadlineExceeded => StatusCode::GATEWAY_TIMEOUT,
            tonic::Code::NotFound => StatusCode::NOT_FOUND,
            tonic::Code::AlreadyExists => StatusCode::CONFLICT,
            tonic::Code::PermissionDenied => StatusCode::FORBIDDEN,
            // XXX No better idea !
            tonic::Code::Cancelled
            | tonic::Code::Aborted
            | tonic::Code::Internal
            | tonic::Code::ResourceExhausted
            | tonic::Code::DataLoss => StatusCode::INTERNAL_SERVER_ERROR,
            tonic::Code::FailedPrecondition => StatusCode::PRECONDITION_FAILED,
            tonic::Code::OutOfRange => StatusCode::BAD_REQUEST,
            tonic::Code::Unimplemented => StatusCode::NOT_IMPLEMENTED,
            tonic::Code::Unavailable => StatusCode::SERVICE_UNAVAILABLE,
            tonic::Code::Unauthenticated => StatusCode::UNAUTHORIZED,
            tonic::Code::Unknown => {
                // Handle rpc error which is out
                // of gRPC namespace.
                // Usually occurs when a non-Qgis error
                // is raised before reaching qgis server.
                // In this case return the error code found in
                // the metadata.
                return Self::from_metadata(status.metadata(), request_id)
                    .content_type("text/plain")
                    .body(status.message().to_string());
            }
        };

        // Send informative message
        HttpResponseBuilder::new(code)
            .content_type("text/plain")
            .body(match code.as_u16() {
                503 => "Service temporary unavailable".to_string(),
                code if code < 500 => status.message().to_string(),
                _ => "Server Error".to_string(),
            })
    }
}

impl RpcResponseFactory for HttpResponseBuilder {}
