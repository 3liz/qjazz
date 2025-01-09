//
// Rpc server
//
use crate::config::Settings;
use crate::service::{QgisAdminServer, QgisAdminServicer, QgisServerServer, QgisServerServicer};
use qjazz_pool::Pool;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tonic::transport::{Identity, Server, ServerTlsConfig};

/// Run gRPC server
pub(crate) async fn serve(
    args: &str,
    settings: &Settings,
) -> Result<(), Box<dyn std::error::Error>> {
    let addr = settings.server.listen().address();

    // see https://github.com/hyperium/tonic/blob/master/examples/src/health/server.rs
    let (mut health_reporter, health_service) = tonic_health::server::health_reporter();

    let mut pool = Pool::new(qjazz_pool::Builder::from_options(
        args.split_ascii_whitespace(),
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

    let signal_handle =
        crate::signals::handle_signals(pool_owned.clone(), token.clone())?;

    let grace_period = settings.server.shutdown_grace_period();

    // NOTE Do not use serve_with_shutdown since
    // it waits forever for client to disconnect
    // Just launch the task and let tokio abort on exit.
    // Furthemore graceful shutdown is handled by the worker
    // pool.
    let mut builder = Server::builder();

    // Enable tls
    if settings.server.enable_tls() {
        log::info!("TLS enabled");
        let cert = settings.server.tls_cert()?;
        let key = settings.server.tls_key()?;
        builder =
            builder.tls_config(ServerTlsConfig::new().identity(Identity::from_pem(cert, key)))?;
    }

    let mut router = builder
        .timeout(settings.server.timeout())
        .add_service(health_service)
        .add_service(QgisServerServer::new(qgis_servicer));

    if settings.server.enable_admin_services() {
        log::info!("Enabling admin services");
        router = router.add_service(QgisAdminServer::new(admin_servicer));
    }

    // Start server
    tokio::spawn(router.serve(addr));

    token.cancelled().await;

    log::debug!("Closing signal handle");
    signal_handle.close();

    // Close queue
    pool_owned.write().await.close(grace_period).await;
    // Notify that we are not serving anymore.
    health_reporter
        .set_not_serving::<QgisServerServer<QgisServerServicer>>()
        .await;

    log::info!("Server shutdown");
    Ok(())
}

