use qjazz_service::{
    project_info, ApiRequest, CacheInfo, CatalogItem, CatalogRequest, CheckoutRequest, DropRequest,
    Empty, JsonConfig, OwsRequest, PingReply, PingRequest, PluginInfo, ProjectInfo, ProjectRequest,
    ResponseChunk, ServerStatus, ServingStatus, SleepRequest, StatsReply,
};

use std::pin::Pin;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio_stream::{wrappers::ReceiverStream, Stream};
use tonic::{Request, Response, Status};

use crate::config::Settings;
use crate::utils::{headers_to_metadata, metadata_to_headers};
use qjazz_pool::restore;

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

    fn get_ref(&self) -> &qjazz_pool::Receiver {
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
use std::sync::Arc;
use tokio::sync::RwLock;
use tonic_health::server::HealthReporter;

// Reexport
pub(crate) use qjazz_service::qgis_admin_server::QgisAdminServer;

pub(crate) struct QgisAdminServicer {
    inner: Inner,
    pool: Arc<RwLock<qjazz_pool::Pool>>,
    health_reporter: HealthReporter,
    uptime: Instant,
}

impl Qjazz for QgisAdminServicer {}

impl QgisAdminServicer {
    pub(crate) fn new(
        queue: qjazz_pool::Receiver,
        pool: Arc<RwLock<qjazz_pool::Pool>>,
        health_reporter: HealthReporter,
    ) -> Self {
        Self {
            inner: Inner(queue),
            pool,
            health_reporter,
            uptime: Instant::now(),
        }
    }
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
        w.done();
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

        // Pull project as reference
        let req = request.into_inner();
        let pull = req.pull.unwrap_or(false);

        let resp = w
            .checkout_project(&req.uri, pull)
            .await
            .map_err(Self::error)?;

        w.done();

        if pull {
            // Trigger sync
            self.inner
                .get_ref()
                .update_cache(restore::State::Pull(req.uri))
                .await;
        }

        Ok(Response::new(resp.into()))
    }

    async fn drop_project(
        &self,
        request: Request<DropRequest>,
    ) -> Result<Response<CacheInfo>, Status> {
        // Get the state of project
        let mut w = self.inner.get_worker().await?;

        let uri = request.into_inner().uri;
        let response = Response::new(
            w.checkout_project(&uri, false)
                .await
                .map(CacheInfo::from)
                .map_err(Self::error)?,
        );

        // Sync state
        self.inner
            .get_ref()
            .update_cache(restore::State::Remove(uri))
            .await;

        Ok(response)
    }

    // List cache
    type ListCacheStream = CacheInfoStream;

    async fn list_cache(
        &self,
        _: Request<Empty>,
    ) -> Result<Response<Self::ListCacheStream>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;

        let (tx, rx) = mpsc::channel(32);
        tokio::spawn(async move {
            {
                let mut stream = match w.list_cache().await {
                    Ok(stream) => stream,
                    Err(err) => {
                        let _ = tx.send(Err(Status::unknown(err))).await;
                        return;
                    }
                };
                loop {
                    if tx
                        .send(match stream.next().await {
                            Ok(Some(item)) => Ok(CacheInfo::from(item)),
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

        let output_stream = ReceiverStream::new(rx);
        Ok(Response::new(
            Box::pin(output_stream) as Self::ListCacheStream
        ))
    }

    // Clear cache
    async fn clear_cache(&self, _: Request<Empty>) -> Result<Response<Empty>, Status> {
        // Sync state
        self.inner
            .get_ref()
            .update_cache(restore::State::Clear)
            .await;

        Ok(Response::new(Empty {}))
    }

    // Update cache
    async fn update_cache(&self, _: Request<Empty>) -> Result<Response<Empty>, Status> {
        // Sync state
        self.inner
            .get_ref()
            .update_cache(restore::State::Update)
            .await;

        Ok(Response::new(Empty {}))
    }
    //
    // Plugins
    //
    type ListPluginsStream = PluginInfoStream;

    async fn list_plugins(
        &self,
        _: Request<Empty>,
    ) -> Result<Response<Self::ListPluginsStream>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;

        let (tx, rx) = mpsc::channel(8);
        tokio::spawn(async move {
            {
                let mut stream = match w.list_plugins().await {
                    Ok(stream) => stream,
                    Err(err) => {
                        let _ = tx.send(Err(Status::unknown(err))).await;
                        return;
                    }
                };
                loop {
                    if tx
                        .send(match stream.next().await {
                            Ok(Some(item)) => Ok(PluginInfo::from(item)),
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

        let output_stream = ReceiverStream::new(rx);
        Ok(Response::new(
            Box::pin(output_stream) as Self::ListPluginsStream
        ))
    }
    //
    // Config managment
    //
    async fn set_config(&self, request: Request<JsonConfig>) -> Result<Response<Empty>, Status> {
        // Sync state
        let patch = serde_json::from_str(&request.into_inner().json)
            .map_err(|err| Status::invalid_argument(format!("{:?}", err)))?;

        if log::log_enabled!(log::Level::Debug) {
            log::debug!("Updating configuration: {}", patch);
        } else {
            log::info!("Updating configuration");
        }

        // Update log level
        Settings::set_log_level(&patch);

        // Patch configuration
        self.pool
            .write()
            .await
            .patch_config(&patch)
            .await
            .map_err(Status::invalid_argument)?;

        self.inner.get_ref().update_config(patch).await;

        Ok(Response::new(Empty {}))
    }

    async fn get_config(&self, _: Request<Empty>) -> Result<Response<JsonConfig>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;
        Ok(Response::new(JsonConfig {
            json: w.get_config().await.map_err(Self::error)?.to_string(),
        }))
    }

    //
    // Project inspection
    //
    async fn get_project_info(
        &self,
        request: Request<ProjectRequest>,
    ) -> Result<Response<ProjectInfo>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;
        let mut resp = w
            .project_info(&request.into_inner().uri)
            .await
            .map_err(Self::error)?;

        w.done();

        Ok(Response::new(ProjectInfo {
            status: resp.status,
            uri: resp.uri,
            filename: resp.filename,
            crs: resp.crs,
            last_modified: resp.last_modified,
            storage: resp.storage,
            has_bad_layers: resp.has_bad_layers,
            layers: resp
                .layers
                .drain(..)
                .map(|l| project_info::Layer {
                    layer_id: l.layer_id,
                    name: l.name,
                    source: l.source,
                    crs: l.crs,
                    is_valid: l.is_valid,
                    is_spatial: l.is_spatial,
                })
                .collect(),
            cache_id: resp.cache_id,
        }))
    }
    // Catalog
    type CatalogStream = CatalogItemStream;

    async fn catalog(
        &self,
        request: Request<CatalogRequest>,
    ) -> Result<Response<Self::CatalogStream>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;
        let location = request.into_inner().location;

        let (tx, rx) = mpsc::channel(32);
        tokio::spawn(async move {
            {
                let mut stream = match w.catalog(location.as_deref()).await {
                    Ok(stream) => stream,
                    Err(err) => {
                        let _ = tx.send(Err(Status::unknown(err))).await;
                        return;
                    }
                };
                loop {
                    if tx
                        .send(match stream.next().await {
                            Ok(Some(item)) => Ok(CatalogItem::from(item)),
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

        let output_stream = ReceiverStream::new(rx);
        Ok(Response::new(Box::pin(output_stream) as Self::CatalogStream))
    }
    //
    // Service managment/inspection
    //
    async fn get_env(&self, _: Request<Empty>) -> Result<Response<JsonConfig>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;
        Ok(Response::new(JsonConfig {
            json: w.get_env().await.map_err(Self::error)?.to_string(),
        }))
    }
    // Change QGIS server serving status
    async fn set_server_serving_status(
        &self,
        request: Request<ServerStatus>,
    ) -> Result<Response<Empty>, Status> {
        // We need a mutable reporter
        let mut reporter = self.health_reporter.clone();

        match request.into_inner().status {
            st if st == ServingStatus::Serving as i32 => {
                reporter
                    .set_serving::<QgisServerServer<QgisServerServicer>>()
                    .await
            }
            st if st == ServingStatus::NotServing as i32 => {
                reporter
                    .set_not_serving::<QgisServerServer<QgisServerServicer>>()
                    .await
            }
            st => {
                return Err(Status::invalid_argument(format!("{}", st)));
            }
        }
        Ok(Response::new(Empty {}))
    }
    // Stats
    async fn stats(&self, _: Request<Empty>) -> Result<Response<StatsReply>, Status> {
        let st = qjazz_pool::stats::Stats::new(self.pool.read().await);
        Ok(Response::new(StatsReply {
            active_workers: st.active_workers() as u64,
            idle_workers: st.idle_workers() as u64,
            activity: st.activity().unwrap_or(0.),
            failure_pressure: st.failure_pressure(),
            request_pressure: st.request_pressure(),
            uptime: self.uptime.elapsed().as_secs(),
        }))
    }
    // Sleep
    async fn sleep(&self, request: Request<SleepRequest>) -> Result<Response<Empty>, Status> {
        // Wait for available worker
        let mut w = self.inner.get_worker().await?;

        w.sleep(request.into_inner().delay)
            .await
            .map_err(Self::error)?;
        Ok(Response::new(Empty {}))
    }
    // Reload
    async fn reload(&self, _: Request<Empty>) -> Result<Response<Empty>, Status> {
        self.inner.get_ref().reload();    
        Ok(Response::new(Empty {}))
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

impl From<qjazz_pool::messages::PluginInfo> for PluginInfo {
    fn from(msg: qjazz_pool::messages::PluginInfo) -> Self {
        PluginInfo {
            name: msg.name,
            path: msg.path,
            plugin_type: msg.plugin_type,
            metadata: msg.metadata.to_string(),
        }
    }
}

impl From<qjazz_pool::messages::CatalogItem> for CatalogItem {
    fn from(msg: qjazz_pool::messages::CatalogItem) -> Self {
        CatalogItem {
            uri: msg.uri,
            name: msg.name,
            storage: msg.storage,
            last_modified: msg.last_modified,
            public_uri: msg.public_uri,
        }
    }
}
