//
// The QGIS Admin servicer
//
use std::sync::Arc;
use tokio::sync::RwLock;
use tonic_health::server::HealthReporter;

use super::*;

use qjazz_service::{
    CacheInfo, CatalogItem, CatalogRequest, CheckoutRequest, DropRequest, DumpCacheItem, Empty,
    JsonConfig, PingReply, PingRequest, PluginInfo, ProjectInfo, ProjectRequest, ServerStatus,
    ServingStatus, SleepRequest, StatsReply, project_info,
};

use qjazz_service::qgis_admin_server::QgisAdmin;

// Reexport
pub use qjazz_service::qgis_admin_server::QgisAdminServer;

pub struct QgisAdminServicer {
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
type DumpCacheItemStream = Pin<Box<dyn Stream<Item = Result<DumpCacheItem, Status>> + Send>>;

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
                .update_cache(
                    if matches!(
                        resp.status,
                        CheckoutStatus::REMOVED | CheckoutStatus::NOTFOUND
                    ) {
                        restore::State::Remove(req.uri)
                    } else {
                        restore::State::Pull(req.uri)
                    },
                )
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

        w.done();

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
                            Ok(Some(item)) => {
                                if !item.pinned {
                                    continue;
                                }
                                Ok(CacheInfo::from(item))
                            }
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

    // Dump cache(s)
    type DumpCacheStream = DumpCacheItemStream;

    async fn dump_cache(
        &self,
        _: Request<Empty>,
    ) -> Result<Response<Self::DumpCacheStream>, Status> {
        let num_workers = self.pool.read().await.options().num_processes();

        // Drain all workers
        // NOTE: This is a kind of 'stop the world' method since it waits
        // for all workers beeing availables
        // should be called only for debugging purposes
        let mut workers = self.inner.get_ref().drain();
        while workers.len() < num_workers {
            workers.push(self.inner.get_worker().await?)
        }

        async fn list_cache(w: &mut qjazz_pool::Worker) -> Result<Vec<CacheInfo>, Status> {
            let mut stream = w.list_cache().await.map_err(QgisAdminServicer::error)?;
            let mut items = vec![];
            loop {
                match stream.next().await {
                    Ok(Some(item)) => items.push(CacheInfo::from(item)),
                    Ok(None) => break,
                    Err(err) => return Err(Status::unknown(err)),
                }
            }
            Ok(items)
        }

        let (tx, rx) = mpsc::channel(32);
        tokio::spawn(async move {
            {
                for mut w in workers.drain(..) {
                    let cache_id = format!("{}_{}", w.name(), w.id().value.unwrap_or(0));
                    let cache = match list_cache(&mut w).await {
                        Ok(cache) => cache,
                        Err(status) => {
                            let _ = tx.send(Err(status)).await;
                            return;
                        }
                    };
                    let config = match w.get_config().await {
                        Ok(config) => config.to_string(),
                        Err(err) => {
                            let _ = tx.send(Err(QgisAdminServicer::error(err))).await;
                            return;
                        }
                    };
                    w.done();
                    if tx
                        .send(Ok(DumpCacheItem {
                            cache_id,
                            config,
                            cache,
                        }))
                        .await
                        .is_err()
                    {
                        log::error!("Connection cancelled by client");
                        return;
                    }
                }
            }
        });

        let output_stream = ReceiverStream::new(rx);
        Ok(Response::new(
            Box::pin(output_stream) as Self::DumpCacheStream
        ))
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
        let patch = serde_json::from_str::<serde_json::Value>(&request.into_inner().json)
            .map_err(|err| Status::invalid_argument(format!("{err:?}")))?;

        if log::log_enabled!(log::Level::Debug) {
            log::debug!("Updating configuration: {patch}");
        } else {
            log::info!("Updating configuration");
        }

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
        Ok(Response::new(JsonConfig {
            json: serde_json::to_string(self.pool.read().await.options())
                .map_err(|err| Status::internal(format!("{err}")))?,
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
        match request.into_inner().status {
            st if st == ServingStatus::Serving as i32 => {
                log::info!("Setting server serving status to SERVING");
                self.health_reporter
                    .set_serving::<QgisServerServer<QgisServerServicer>>()
                    .await
            }
            st if st == ServingStatus::NotServing as i32 => {
                log::info!("Setting server serving status to NOT SERVING");
                self.health_reporter
                    .set_not_serving::<QgisServerServer<QgisServerServicer>>()
                    .await
            }
            st => {
                return Err(Status::invalid_argument(format!("{st}")));
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

        // Remember pid (for testing)
        w.remember().await;
        w.sleep(request.into_inner().delay)
            .await
            .map_err(Self::error)?;
        w.done();
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
