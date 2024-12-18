use qjazz_service::qgis_server_server::QgisServer;
use qjazz_service::{ApiRequest, OwsRequest, PingReply, PingRequest, ResponseChunk};

use std::collections::HashMap;
use std::pin::Pin;
use std::str::FromStr;
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, Stream};
use tonic::{
    metadata::{AsciiMetadataValue, KeyAndValueRef, MetadataKey, MetadataMap},
    Request, Response, Status,
};

mod qjazz_service {
    tonic::include_proto!("qjazz"); // proto package
}

// Reexport
pub(crate) use qjazz_service::qgis_server_server::QgisServerServer;

pub(crate) struct QgisServerServicer {
    inner: Inner,
}

impl QgisServerServicer {
    pub(crate) fn new(queue: qjazz_pool::Receiver) -> Self {
        Self {
            inner: Inner(queue),
        }
    }

    // Handle byte streaming
    fn stream_bytes(
        mut w: qjazz_pool::ScopedWorker,
    ) -> mpsc::Receiver<Result<ResponseChunk, Status>> {
        let (tx, rx) = mpsc::channel(1);
        tokio::spawn(async move {
            {
                let mut stream = match w.byte_stream() {
                    Ok(stream) => stream,
                    Err(err) => {
                        let _ = tx.send(Err(Status::unknown(err))).await;
                        return;
                    }
                };
                loop {
                    if tx
                        .send(match stream.next().await {
                            Ok(Some(chunk)) => Ok(ResponseChunk {
                                chunk: chunk.into(),
                            }),
                            Ok(None) => break,
                            Err(err) => Err(Status::unknown(err)),
                        })
                        .await
                        .is_err()
                    {
                        log::error!("Connection cancelled by client");
                        return;
                    }
                }
            }
            w.done();
        });
        rx
    }
}

type ResponseChunkStream = Pin<Box<dyn Stream<Item = Result<ResponseChunk, Status>> + Send>>;

#[tonic::async_trait]
impl QgisServer for QgisServerServicer {
    //
    // Ping
    //
    async fn ping(&self, request: Request<PingRequest>) -> Result<Response<PingReply>, Status> {
        let reply = PingReply {
            echo: request.into_inner().echo,
        };
        Ok(Response::new(reply))
    }

    // Ows request
    type ExecuteOwsRequestStream = ResponseChunkStream;

    async fn execute_ows_request(
        &self,
        request: Request<OwsRequest>,
    ) -> Result<Response<Self::ExecuteOwsRequestStream>, Status> {
        let mut w = self.inner.get_worker().await?;

        let headers = metadata_to_dict(request.metadata());
        let req = request.get_ref();
        let mut resp = w
            .request(qjazz_pool::messages::OwsRequestMsg {
                service: &req.service,
                request: &req.request,
                target: &req.target,
                url: req.url.as_deref(),
                version: req.version.as_deref(),
                direct: req.direct.unwrap_or(false),
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                debug_report: req.debug_report.unwrap_or(false),
                headers,
            })
            .await
            .map_err(from_response_err)?;

        let rx = Self::stream_bytes(w);

        let output_stream = ReceiverStream::new(rx);
        let mut response = Response::new(Box::pin(output_stream) as Self::ExecuteOwsRequestStream);

        set_metadata(response.metadata_mut(), resp.status_code, &mut resp.headers);
        Ok(response)
    }

    // Api request
    type ExecuteApiRequestStream = ResponseChunkStream;

    async fn execute_api_request(
        &self,
        request: Request<ApiRequest>,
    ) -> Result<Response<Self::ExecuteApiRequestStream>, Status> {
        let mut w = self.inner.get_worker().await?;
        let headers = metadata_to_dict(request.metadata());
        let req = request.get_ref();
        let mut resp = w
            .request(qjazz_pool::messages::ApiRequestMsg {
                name: &req.name,
                path: &req.path,
                method: req
                    .method
                    .as_str()
                    .try_into()
                    .map_err(Status::invalid_argument)?,
                url: req.url.as_deref(),
                data: req.data.as_deref(),
                delegate: req.delegate.unwrap_or(false),
                target: req.target.as_deref(),
                direct: req.direct.unwrap_or(false),
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                debug_report: req.debug_report.unwrap_or(false),
                headers,
            })
            .await
            .map_err(from_response_err)?;

        let rx = Self::stream_bytes(w);

        let output_stream = ReceiverStream::new(rx);
        let mut response = Response::new(Box::pin(output_stream) as Self::ExecuteApiRequestStream);

        set_metadata(response.metadata_mut(), resp.status_code, &mut resp.headers);
        Ok(response)
    }
}

//
// Wrapper for queue
//
struct Inner(qjazz_pool::Receiver);

impl Inner {
    // wait for available worker
    async fn get_worker(&self) -> Result<qjazz_pool::ScopedWorker, Status> {
        self.0.get().await.map_err(|err| match err {
            qjazz_pool::Error::MaxRequestsExceeded => Status::resource_exhausted(err),
            qjazz_pool::Error::QueueIsClosed => Status::unavailable(err),
            _ => Status::unknown(err),
        })
    }
}

// HEADERS
// XXX Fix metadata <-> headers handling

fn metadata_to_dict(metadata: &MetadataMap) -> HashMap<String, String> {
    HashMap::from_iter(metadata.iter().filter_map(|key_value| {
        match key_value {
            KeyAndValueRef::Ascii(key, value) => value
                .to_str()
                .map(|v| (key.as_str().to_string(), v.to_string()))
                .ok(),
            _ => None,
        }
    }))
}

/// Handle response error
fn from_response_err(err: qjazz_pool::Error) -> Status {
    match err {
        qjazz_pool::Error::ResponseError(status, msg) => {
            let mut rv = match status {
                404 | 410 => Status::not_found(msg.to_string()),
                403 => Status::permission_denied(msg.to_string()),
                500 => Status::internal(msg.to_string()),
                401 => Status::unauthenticated(msg.to_string()),
                _ => Status::unknown(format!("Response error {}: {}", status, msg)),
            };
            rv.metadata_mut()
                .insert("x-reply-status-code", status.into());
            rv
        }
        _ => Status::unknown(err),
    }
}

fn set_metadata(metadata: &mut MetadataMap, status: i64, headers: &mut HashMap<String, String>) {
    metadata.insert("x-reply-status-code", status.into());
    for (k, v) in headers.iter() {
        if let Ok(v) = AsciiMetadataValue::from_str(v) {
            let mut k = format!("x-reply-header-{k}");
            k.make_ascii_lowercase();
            if let Ok(k) = MetadataKey::from_str(&k) {
                metadata.insert(k, v);
            } else {
                log::error!("Invalid response header key {:?}", k);
            }
        } else {
            log::error!("Invalid response header value {:?}", v);
        }
    }
}
