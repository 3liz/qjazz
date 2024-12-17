//
// Rpc server
//
use crate::service::{QgisServerServer, QgisServerServicer};
use qjazz_pool::Pool;
use std::ffi::OsStr;
use tonic::transport::Server;

/// Run gRPC server
pub(crate) async fn serve<I, S>(
    args: I,
    settings: &crate::config::Settings,
) -> Result<(), Box<dyn std::error::Error>>
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    let addr = settings.server.listen.address();

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

    // NOTE: service are registered as "qjazz.<service name>"
    // While in python this is "<service name>

    let servicer = QgisServerServicer::new(qjazz_pool::Receiver::new(&pool));
    Server::builder()
        .add_service(health_service)
        .add_service(QgisServerServer::new(servicer))
        .serve(addr)
        //.serve_with_shutdown(addr, pool.close())
        .await?;

    log::info!("Server shutdown");

    Ok(())
}
