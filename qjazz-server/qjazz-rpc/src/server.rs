//
// Rpc server
//
use crate::config::Settings;
use crate::service::admin::{QgisAdminServer, QgisAdminServicer};
use crate::service::{QgisServerServer, QgisServerServicer};
use qjazz_pool::Pool;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tonic::transport::{Certificate, Identity, Server, ServerTlsConfig};

/// Run gRPC server
pub(crate) async fn serve(
    args: String,
    settings: &Settings,
) -> Result<(), Box<dyn std::error::Error>> {
    let addr = settings.rpc.listen().address();

    // see https://github.com/hyperium/tonic/blob/master/examples/src/health/server.rs
    let (mut health_reporter, health_service) = tonic_health::server::health_reporter();

    let mut pool = Pool::new(qjazz_pool::Builder::from_options(
        args,
        settings.worker.clone(),
    ));
    pool.maintain_pool().await?;

    health_reporter
        .set_serving::<QgisServerServer<QgisServerServicer>>()
        .await;

    let receiver = qjazz_pool::Receiver::new(&pool);

    // NOTE: service are registered as "qjazz.<service name>"
    // While in python this is "<service name>
    let qgis_servicer = QgisServerServicer::new(receiver.clone());

    // Create admin servicer
    let pool_owned = Arc::new(RwLock::new(pool));
    let admin_servicer =
        QgisAdminServicer::new(receiver, pool_owned.clone(), health_reporter.clone());

    // Handle graceful shutdown
    let token = CancellationToken::new();

    let signal_handle = crate::signals::handle_signals(
        pool_owned.clone(),
        token.clone(),
        settings.rpc.max_failure_pressure(),
    )?;

    let oom_killer = crate::oom::handle_oom(
        pool_owned.clone(),
        token.clone(),
        settings.rpc.high_water_mark(),
        settings.rpc.oom_period(),
    )?;

    let grace_period = settings.rpc.shutdown_grace_period();

    // NOTE Do not use serve_with_shutdown since
    // it waits forever for client to disconnect
    // Just launch the task and let tokio abort on exit.
    // Furthemore graceful shutdown is handled by the worker
    // pool.
    let mut builder = Server::builder();

    // Enable tls
    if settings.rpc.enable_tls() {
        log::info!("TLS enabled");
        let cert = settings.rpc.tls_cert()?;
        let key = settings.rpc.tls_key()?;

        let mut tls = ServerTlsConfig::new().identity(Identity::from_pem(cert, key));
        if let Some(cacert) = settings.rpc.tls_client_ca() {
            tls = tls.client_ca_root(Certificate::from_pem(cacert?));
        }

        builder = builder.tls_config(tls)?;
    }

    let mut router = builder
        .timeout(settings.rpc.timeout())
        .add_service(health_service)
        .add_service(QgisServerServer::new(qgis_servicer));

    if settings.rpc.enable_admin_services() {
        log::info!("Enabling admin services");
        router = router.add_service(QgisAdminServer::new(admin_servicer));
    }

    // Start server
    log::info!("RPC serving at {}", addr);
    tokio::spawn(router.serve(addr));

    token.cancelled().await;

    // Wait for oom killer termination
    oom_killer.abort();
    let _ = oom_killer.await;

    log::debug!("Closing signal handle");
    signal_handle.close();

    // Close queue
    pool_owned.write().await.close(grace_period).await;

    // Notify that we are not serving anymore.
    health_reporter
        .set_not_serving::<QgisServerServer<QgisServerServicer>>()
        .await;

    log::info!("Server shutdown");
    if pool_owned.write().await.has_error() {
        Err("Server terminated because of errors".into())
    } else {
        Ok(())
    }
}
