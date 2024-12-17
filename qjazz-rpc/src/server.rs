//
// Rpc server
//
use crate::config::Settings;
use crate::service::{QgisServerServer, QgisServerServicer};
use qjazz_pool::Pool;
use std::ffi::OsStr;
use std::time::Duration;
use tonic::transport::Server;
use tokio_util::sync::CancellationToken;

/// Run gRPC server
pub(crate) async fn serve(
    args: &str,
    settings: &Settings,
) -> Result<(), Box<dyn std::error::Error>> {
    let addr = settings.server.listen.address();

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

    // NOTE: service are registered as "qjazz.<service name>"
    // While in python this is "<service name>
    let servicer = QgisServerServicer::new(qjazz_pool::Receiver::new(&pool));
    
    // Handle graceful shutdown
    let token = CancellationToken::new();
    let signal_handle = crate::signals::handle_signals(token.clone())?;

    let grace_period = Duration::from_secs(settings.server.shutdown_grace_period);

    Server::builder()
        .add_service(health_service)
        .add_service(QgisServerServer::new(servicer))
        //..serve(addr)
        .serve_with_shutdown(addr, async move {
            token.cancelled().await;
            pool.close(grace_period).await;
            log::debug!("Shutdown finalized");
        })
        .await?;
  
    log::debug!("Closing signal handle");
    signal_handle.close();

    log::info!("Server shutdown");
    Ok(())
}
