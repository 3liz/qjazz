use qjazz_service::{
    ApiRequest, CacheInfo, CatalogItem, CatalogRequest, CheckoutRequest, DropRequest, Empty,
    JsonConfig, ListRequest, OwsRequest, PingReply, PingRequest, PluginInfo, ProjectInfo,
    ProjectRequest, ResponseChunk, ServerStatus, SleepRequest, StatsReply,
};

use std::pin::Pin;
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, Stream};
use tonic::{Request, Response, Status};

use crate::utils::{headers_to_metadata, metadata_to_headers};

// Qjazz gRPC services

mod qjazz_service {
    tonic::include_proto!("qjazz"); // proto package
}

//
// Wrapper for worker queue
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
                direct: req.direct.unwrap_or(false),
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                header_prefix: Some(Self::HEADER_PREFIX),
                debug_report: false,
                headers,
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
                delegate: req.delegate.unwrap_or(false),
                target: req.target.as_deref(),
                direct: req.direct.unwrap_or(false),
                options: req.options.as_deref(),
                request_id: req.request_id.as_deref(),
                header_prefix: Some(Self::HEADER_PREFIX),
                debug_report: false,
                headers,
            })
            .await
            .map_err(Self::error)?;

        let rx = Self::stream_bytes(w);

        let output_stream = ReceiverStream::new(rx);
        let mut response = Response::new(Box::pin(output_stream) as Self::ExecuteApiRequestStream);

        headers_to_metadata(response.metadata_mut(), resp.status_code, &resp.headers);
        Ok(response)
    }
}

//
// The QGIS Admin servicer
//

use qjazz_service::qgis_admin_server::QgisAdmin;
// Reexport
pub(crate) use qjazz_service::qgis_admin_server::QgisAdminServer;

pub(crate) struct QgisAdminServicer {
    inner: Inner,
}

impl Qjazz for QgisAdminServicer {}

impl QgisAdminServicer {
    pub(crate) fn new(queue: qjazz_pool::Receiver) -> Self {
        Self {
            inner: Inner(queue),
        }
    }
    /*
    // Handle byte streaming
    fn stream_object<R, T>(qjazz
        mut _w: qjazz_pool::ScopedWorker,
    ) -> mpsc::Receiver<Result<T, Status>>
    where
        T: From<
    {
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
    */
}

type CacheInfoStream = Pin<Box<dyn Stream<Item = Result<CacheInfo, Status>> + Send>>;
type PluginInfoStream = Pin<Box<dyn Stream<Item = Result<PluginInfo, Status>> + Send>>;
type CatalogItemStream = Pin<Box<dyn Stream<Item = Result<CatalogItem, Status>> + Send>>;

// gRPC Service implementation
#[tonic::async_trait]
impl QgisAdmin for QgisAdminServicer {
    //
    // Ping
    //
    async fn ping(&self, request: Request<PingRequest>) -> Result<Response<PingReply>, Status> {
        let mut w = self.inner.get_worker().await?;
        let echo = w
            .ping(&request.into_inner().echo)
            .await
            .map_err(Self::error)?;
        Ok(Response::new(PingReply { echo }))
    }
    //
    // Cache managment
    //
    async fn checkout_project(
        &self,
        request: Request<CheckoutRequest>,
    ) -> Result<Response<CacheInfo>, Status> {
        let mut w = self.inner.get_worker().await?;

        let req = request.get_ref();
        let resp = w
            .checkout_project(&req.uri, req.pull.unwrap_or(false))
            .await
            .map_err(Self::error)?;

        Ok(Response::new(resp.into()))
    }
    // Pull project
    type PullProjectsStream = CacheInfoStream;

    // We need to sync all workers with the same data
    // 1. Update the restore state for busy workers (Write lock)
    // 2. Drain all idle workers
    // 3. Unlock the restore state
    // 4. Release all workers
    async fn pull_projects(
        &self,
        request: Request<tonic::Streaming<ProjectRequest>>,
    ) -> Result<Response<Self::PullProjectsStream>, Status> {
        /*
        let mut in_stream = request.into_inner();

        let (tx, rx) = mpsc::channel(64);
        */
        Err(Status::unimplemented(""))
    }
    // Drop project
    type DropProjectStream = CacheInfoStream;

    async fn drop_project(
        &self,
        request: Request<DropRequest>,
    ) -> Result<Response<Self::DropProjectStream>, Status> {
        Err(Status::unimplemented(""))
    }
    // List cache
    type ListCacheStream = CacheInfoStream;

    async fn list_cache(
        &self,
        request: Request<ListRequest>,
    ) -> Result<Response<Self::ListCacheStream>, Status> {
        Err(Status::unimplemented(""))
    }
    // Clear cache
    async fn clear_cache(&self, request: Request<Empty>) -> Result<Response<Empty>, Status> {
        Err(Status::unimplemented(""))
    }
    // Update cache
    type UpdateCacheStream = CacheInfoStream;

    async fn update_cache(
        &self,
        request: Request<Empty>,
    ) -> Result<Response<Self::UpdateCacheStream>, Status> {
        Err(Status::unimplemented(""))
    }
    //
    // Plugins
    //
    type ListPluginsStream = PluginInfoStream;

    async fn list_plugins(
        &self,
        request: Request<Empty>,
    ) -> Result<Response<Self::ListPluginsStream>, Status> {
        Err(Status::unimplemented(""))
    }
    //
    // Config managment
    //
    async fn set_config(&self, request: Request<JsonConfig>) -> Result<Response<Empty>, Status> {
        Err(Status::unimplemented(""))
    }
    async fn get_config(&self, request: Request<Empty>) -> Result<Response<JsonConfig>, Status> {
        Err(Status::unimplemented(""))
    }
    async fn reload_config(&self, request: Request<Empty>) -> Result<Response<Empty>, Status> {
        Err(Status::unimplemented(""))
    }
    //
    // Project inspection
    //
    async fn get_project_info(
        &self,
        request: Request<ProjectRequest>,
    ) -> Result<Response<ProjectInfo>, Status> {
        Err(Status::unimplemented(""))
    }
    // Catalog
    type CatalogStream = CatalogItemStream;

    async fn catalog(
        &self,
        request: Request<CatalogRequest>,
    ) -> Result<Response<Self::CatalogStream>, Status> {
        Err(Status::unimplemented(""))
    }
    //
    // Service managment/inspection
    //
    async fn get_env(&self, request: Request<Empty>) -> Result<Response<JsonConfig>, Status> {
        Err(Status::unimplemented(""))
    }
    async fn set_server_serving_status(
        &self,
        request: Request<ServerStatus>,
    ) -> Result<Response<Empty>, Status> {
        Err(Status::unimplemented(""))
    }
    async fn stats(&self, request: Request<Empty>) -> Result<Response<StatsReply>, Status> {
        Err(Status::unimplemented(""))
    }
    async fn sleep(&self, request: Request<SleepRequest>) -> Result<Response<Empty>, Status> {
        Err(Status::unimplemented(""))
    }
}

// Converters

impl From<qjazz_pool::messages::CacheInfo> for CacheInfo {
    fn from(msg: qjazz_pool::messages::CacheInfo) -> Self {
        CacheInfo {
            uri: msg.uri,
            status: msg.status,
            in_cache: msg.in_cache,
            timestamp: msg.timestamp,
            name: msg.name,
            storage: msg.storage,
            last_modified: msg.last_modified,
            saved_version: msg.saved_version,
            debug_metadata: msg.debug_metadata,
            cache_id: msg.cache_id,
            last_hit: msg.last_hit,
            hits: msg.hits,
            pinned: msg.pinned,
        }
    }
}
