use std::pin::Pin;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, Stream};
use tonic::{Request, Response, Status};

use crate::config::Settings;
use crate::utils::{headers_to_metadata, metadata_to_headers};
use qjazz_pool::restore;

// Qjazz gRPC services

pub mod qjazz_service {
    tonic::include_proto!("qjazz"); // proto package
}

use qjazz_service::{
    collections_page::CollectionsItem, ApiRequest, CollectionsPage, CollectionsRequest,
    CollectionsType, OwsRequest, PingReply, PingRequest, ResponseChunk,
};

pub mod admin;

//
// Wrapper for worker queue
//
pub struct Inner(qjazz_pool::Receiver);

impl Inner {
    // wait for available worker
    pub async fn get_worker(&self) -> Result<qjazz_pool::ScopedWorker, Status> {
        self.0.get().await.map_err(|err| match err {
            qjazz_pool::Error::MaxRequestsExceeded => Status::resource_exhausted(err),
            qjazz_pool::Error::QueueIsClosed => Status::unavailable(err),
            _ => Status::unknown(err),
        })
    }

    pub fn get_ref(&self) -> &qjazz_pool::Receiver {
        &self.0
    }
}

//
// Helper trait
//
trait Qjazz {
    const HEADER_PREFIX: &str = "x-reply-header-";

    // Handle response error
    // Convert process status response to gRPC response
    // whenever it is possible.
    fn error(err: qjazz_pool::Error) -> Status {
        match err {
            qjazz_pool::Error::ResponseError(code, msg) => match code {
                404 | 410 => Status::not_found(msg.to_string()),
                403 => Status::permission_denied(msg.to_string()),
                500 => Status::internal(msg.to_string()),
                401 => Status::unauthenticated(msg.to_string()),
                _ => {
                    let mut status = Status::unknown(msg.to_string());
                    status
                        .metadata_mut()
                        .insert("x-reply-status-code", code.into());
                    status
                }
            },
            _ => Status::unknown(err),
        }
    }
}

//
// The QGIS Server servicer
//
// Handle QGIS requests
//
use qjazz_service::qgis_server_server::QgisServer;
// Reexport
pub(crate) use qjazz_service::qgis_server_server::QgisServerServer;

pub(crate) struct QgisServerServicer {
    inner: Inner,
}

impl Qjazz for QgisServerServicer {}

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

// gRPC Service implementation
#[tonic::async_trait]
impl QgisServer for QgisServerServicer {
    //
    // Ping
    //
    async fn ping(&self, request: Request<PingRequest>) -> Result<Response<PingReply>, Status> {
        let mut w = self.inner.get_worker().await?;
        let echo = w
            .ping(&request.into_inner().echo)
            .await
            .map_err(Self::error)?;
        w.done();
        Ok(Response::new(PingReply { echo }))
    }
    //
    // Ows request
    //
    type ExecuteOwsRequestStream = ResponseChunkStream;

    async fn execute_ows_request(
        &self,
        request: Request<OwsRequest>,
    ) -> Result<Response<Self::ExecuteOwsRequestStream>, Status> {
        let mut w = self.inner.get_worker().await?;

        let headers = metadata_to_headers(request.metadata());
        let req = request.get_ref();
        let resp = w
            .request(qjazz_pool::messages::OwsRequestMsg {
                service: &req.service,
                request: &req.request,
                target: &req.target,
                url: req.url.as_deref(),
                version: req.version.as_deref(),
                direct: req.direct,
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                header_prefix: Some(Self::HEADER_PREFIX),
                debug_report: false,
                headers,
                content_type: req.content_type.as_deref(),
                method: req
                    .method
                    .as_deref()
                    .map(|me| me.try_into().map_err(Status::invalid_argument))
                    .transpose()?,
                body: req.body.as_deref(),
            })
            .await
            .map_err(Self::error)?;

        let rx = Self::stream_bytes(w);

        let output_stream = ReceiverStream::new(rx);
        let mut response = Response::new(Box::pin(output_stream) as Self::ExecuteOwsRequestStream);

        headers_to_metadata(response.metadata_mut(), resp.status_code, &resp.headers);
        Ok(response)
    }
    //
    // Api request
    //
    type ExecuteApiRequestStream = ResponseChunkStream;

    async fn execute_api_request(
        &self,
        request: Request<ApiRequest>,
    ) -> Result<Response<Self::ExecuteApiRequestStream>, Status> {
        let mut w = self.inner.get_worker().await?;
        let headers = metadata_to_headers(request.metadata());
        let req = request.get_ref();
        let resp = w
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
                delegate: req.delegate,
                target: req.target.as_deref(),
                direct: req.direct,
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                header_prefix: Some(Self::HEADER_PREFIX),
                debug_report: false,
                headers,
                content_type: req.content_type.as_deref(),
            })
            .await
            .map_err(Self::error)?;

        let rx = Self::stream_bytes(w);

        let output_stream = ReceiverStream::new(rx);
        let mut response = Response::new(Box::pin(output_stream) as Self::ExecuteApiRequestStream);

        headers_to_metadata(response.metadata_mut(), resp.status_code, &resp.headers);
        Ok(response)
    }
    //
    // Collections
    //

    async fn collections(
        &self,
        request: Request<CollectionsRequest>,
    ) -> Result<Response<CollectionsPage>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;

        let msg = request.into_inner();
        Ok(Response::new(CollectionsPage::from(
            w.collections(
                msg.location.as_deref(),
                match msg.r#type {
                    t if t == CollectionsType::Catalog as i32 => {
                        qjazz_pool::messages::CollectionsType::CATALOG
                    }
                    t if t == CollectionsType::Dataset as i32 => {
                        qjazz_pool::messages::CollectionsType::DATASET
                    }
                    t => {
                        return Err(Status::internal(format!("Invalid collection type: {}", t)));
                    }
                },
                msg.start..msg.end,
            )
            .await
            .map_err(Self::error)?,
        )))
    }
}

impl From<qjazz_pool::messages::CollectionsPage> for CollectionsPage {
    fn from(mut msg: qjazz_pool::messages::CollectionsPage) -> Self {
        CollectionsPage {
            schema: msg.schema,
            next: msg.next,
            items: msg.items.drain(..).map(CollectionsItem::from).collect(),
        }
    }
}

impl From<qjazz_pool::messages::CollectionsItem> for CollectionsItem {
    fn from(msg: qjazz_pool::messages::CollectionsItem) -> Self {
        CollectionsItem {
            name: msg.name,
            json: msg.json,
            endpoints: msg.endpoints.bits(),
        }
    }
}
