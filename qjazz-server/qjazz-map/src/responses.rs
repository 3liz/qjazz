//!
//! Response utilities
//!

use actix_web::{error, http::StatusCode, web};
use futures::stream::{self, Stream, StreamExt};

use crate::channel::Channel;

use std::hash::{DefaultHasher, Hash, Hasher};

pub fn undisclosed_uri(s: &String) -> String {
    let mut hasher = DefaultHasher::new();
    s.hash(&mut hasher);
    format!("undisclosed{:X}", hasher.finish())
}

pub enum HttpStatusCode {
    Rpc(StatusCode),
    User(StatusCode),
}

impl HttpStatusCode {
    pub fn code(&self) -> StatusCode {
        match self {
            Self::Rpc(code) => *code,
            Self::User(code) => *code,
        }
    }

    fn from_rpc_status(status: &tonic::Status) -> Self {
        use HttpStatusCode::*;

        match status.code() {
            tonic::Code::DeadlineExceeded => Rpc(StatusCode::GATEWAY_TIMEOUT),
            tonic::Code::PermissionDenied => Rpc(StatusCode::FORBIDDEN),
            // XXX Cancelled is usually a response to an action from the caller.
            // Having this error here means that some external cause occured on
            // service side.
            tonic::Code::Cancelled => Rpc(StatusCode::SERVICE_UNAVAILABLE),
            tonic::Code::Internal | tonic::Code::ResourceExhausted => {
                Rpc(StatusCode::INTERNAL_SERVER_ERROR)
            }
            tonic::Code::Unimplemented => Rpc(StatusCode::NOT_IMPLEMENTED),
            tonic::Code::Unavailable => Rpc(StatusCode::SERVICE_UNAVAILABLE),
            tonic::Code::Unauthenticated => Rpc(StatusCode::UNAUTHORIZED),

            // User code generated errors
            // see https://grpc.io/docs/guides/status-codes
            //
            // Usually occurs when a non-Qgis error
            // is raised before reaching qgis server.
            code => User(match code {
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
            }),
        }
    }
}

impl From<tonic::Status> for HttpStatusCode {
    fn from(status: tonic::Status) -> Self {
        Self::from_rpc_status(&status)
    }
}

impl From<&tonic::Status> for HttpStatusCode {
    fn from(status: &tonic::Status) -> Self {
        Self::from_rpc_status(status)
    }
}

pub fn json_collection_stream<T, S>(
    stream: S,
    channel: web::Data<Channel>,
) -> impl Stream<Item = Result<web::Bytes, error::Error>>
where
    T: serde::Serialize,
    S: Stream<Item = Result<T, tonic::Status>>,
{
    let mut comma = false;
    let mut buf: Vec<u8> = vec![];

    stream::once(async { Ok(web::Bytes::from("{ \"items\": [")) })
        .chain(stream.map(move |resp| match resp {
            Ok(item) => {
                buf.clear();
                if comma {
                    buf.push(b',')
                } else {
                    comma = true
                };
                match serde_json::to_writer(&mut buf, &item) {
                    Ok(()) => Ok(web::Bytes::from(buf.clone())),
                    Err(err) => {
                        log::error!("{err}");
                        Err(error::ErrorInternalServerError("Internal server error"))
                    }
                }
            }
            Err(status) => {
                log::error!("Backend streaming error:\t{}\t{status}", channel.name());
                Err(error::ErrorInternalServerError("Internal server error"))
            }
        }))
        .chain(stream::once(async { Ok(web::Bytes::from("]}")) }))
}

//pub type ResponseStream<T> = tonic::Response<tonic::Streaming<T>>;
/*
pub mod metadata {
    use actix_web::error;
    use std::str::FromStr;
    use tonic::metadata::{MetadataKey, MetadataMap, MetadataValue};

    pub fn insert_header(md: &mut MetadataMap, key: &str, value: &str) -> Result<(), error::Error> {

        fn internal_error<E: std::error::Error>(err: E) -> error::Error {
            log::error!("{err}");
            error::ErrorInternalServerError("Internal error")
        }

        MetadataKey::from_str(key)
            .map_err(internal_error)
            .and_then(|k| {
                MetadataValue::from_str(value)
                    .map_err(internal_error)
                    .map(|v| {
                        md.insert(k, v);
                    })
            })
    }
}
*/
