//!
//! Backend gRPC channel
//!

use actix_web::web;
use ginepro::{LoadBalancedChannel, ServiceDefinition};
use tonic::{Code, Status};
use tonic_health::pb::{
    health_check_response::ServingStatus, health_client::HealthClient, HealthCheckRequest,
};

use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::time::Duration;
use tokio_util::sync::CancellationToken;

// Reexport
pub use crate::resolver::{ApiEndPoint, ChannelConfig};

// Qjazz gRPC services
pub mod qjazz_service {
    tonic::include_proto!("qjazz");
}

use qjazz_service::qgis_server_client::QgisServerClient;

pub type Error = Status;

pub struct Builder {
    name: String,
    config: ChannelConfig,
}

pub struct Channel {
    name: String,
    config: ChannelConfig,
    // Make endpoints directly usable as
    // App shared data
    endpoints: Vec<web::Data<ApiEndPoint>>,
    serving: Arc<AtomicBool>,
    channel: LoadBalancedChannel,
}

impl Builder {
    pub fn new(name: String, config: ChannelConfig) -> Self {
        Self { name, config }
    }

    pub async fn connect(mut self) -> Result<Channel, Error> {
        log::debug!(
            "Confguring backend '{}' at {:?}",
            self.name,
            self.config.service()
        );

        Channel::connect(&self.config).await.map(|channel| Channel {
            name: self.name,
            endpoints: self.config.api.drain(..).map(web::Data::new).collect(),
            config: self.config,
            serving: Arc::new(AtomicBool::new(false)),
            channel,
        })
    }
}

fn service_definition(cfg: &ChannelConfig) -> Result<ServiceDefinition, Error> {
    ServiceDefinition::try_from(cfg.service())
        .map_err(|e| Status::internal(format!("Cannot build service definition {:?}", e)))
}

impl Channel {
    pub fn builder(name: String, conf: ChannelConfig) -> Builder {
        Builder::new(name, conf)
    }

    async fn connect(conf: &ChannelConfig) -> Result<LoadBalancedChannel, Error> {
        let builder = LoadBalancedChannel::builder(service_definition(conf)?);

        if conf.enable_tls() {
            builder.with_tls(
                conf.tls_config()
                    .map_err(|e| Status::internal(format!("Client certificat error {:?}", e)))?,
            )
        } else {
            builder
        }
        .dns_probe_interval(conf.probe_interval())
        .channel()
        .await
        .map_err(|e| Status::internal(format!("Failed to create load balanced channel {}", e)))
    }

    pub fn serving(&self) -> bool {
        self.serving.load(Ordering::Relaxed)
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn title(&self) -> &str {
        &self.config.title
    }

    pub fn description(&self) -> &str {
        &self.config.description
    }

    pub fn route(&self) -> &str {
        &self.config.route
    }

    pub fn allow_direct_resolution(&self) -> bool {
        self.config.allow_direct_resolution
    }

    /// Return a client stub interface for service
    pub fn client(&self) -> QgisServerClient<LoadBalancedChannel> {
        QgisServerClient::new(self.channel.clone())
    }

    pub fn api_endpoints(&self) -> &[web::Data<ApiEndPoint>] {
        self.endpoints.as_slice()
    }

    /// Header filter predicate
    pub fn allow_header(&self, key: &str) -> bool {
        self.config.forward_headers.apply(key)
    }

    /// Request timeout
    /// See https://docs.rs/tonic/latest/tonic/struct.Request.html#method.set_timeout
    pub fn timeout(&self) -> Duration {
        self.config.timeout()
    }

    /// Haltch check for the backend
    ///
    /// Run in background, watching for health check status
    /// of the service.
    pub fn watch(&self, token: CancellationToken) {
        let request = HealthCheckRequest {
            service: "qjazz.QgisServer".into(),
        };
        let serving = self.serving.clone();
        let channel = self.channel.clone();
        let name = self.name.clone();
        let sleep_interval = self.config.probe_interval();

        let future = async move {
            let mut available: Option<bool> = None;
            loop {
                let mut stub = HealthClient::new(channel.clone());
                let rv = match stub.watch(request.clone()).await {
                    Err(status) => Some(status),
                    Ok(mut resp) => {
                        available = Some(true);
                        loop {
                            // Handle healthcheck messages
                            match resp.get_mut().message().await {
                                Err(status) => break Some(status),
                                Ok(Some(status)) => match status.status {
                                    st if st == ServingStatus::Serving as i32 => {
                                        log::info!("Backend: {}: status changed to SERVING", name);
                                        serving.store(true, Ordering::Relaxed);
                                    }
                                    st if st == ServingStatus::NotServing as i32 => {
                                        log::info!(
                                            "Backend: {}: status changed to NOT SERVING",
                                            name
                                        );
                                        serving.store(false, Ordering::Relaxed);
                                    }
                                    _ => {
                                        log::info!("Backend: {}: status changed to UNKNOWN", name);
                                        serving.store(false, Ordering::Relaxed);
                                    }
                                },
                                Ok(None) => {
                                    log::info!("Backend: {}: No status", name);
                                    break None;
                                }
                            }
                        }
                    }
                };
                // Handle error
                serving.store(false, Ordering::Relaxed);
                if let Some(status) = rv {
                    if status.code() != Code::Unavailable {
                        log::error!("Backend error:\t{}\t{}", name, status);
                    } else if matches!(available, Some(true) | None) {
                        available = Some(false);
                        log::error!("Backend {}: UNAVAILABLE", name);
                    }
                }
                // Wait before reconnection attempt
                tokio::time::sleep(sleep_interval).await;
            }
        };

        actix_web::rt::spawn(async move { token.run_until_cancelled(future).await });
    }
}
