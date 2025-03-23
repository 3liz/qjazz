use core::net::SocketAddr;
use serde::{Deserialize, Serialize};
use std::fmt::Display;
use std::net::{IpAddr, Ipv4Addr};
use std::path::{Path, PathBuf};
use std::{ffi::OsStr, fs};

use crate::cors::CorsConfig;
use crate::logger::Logging;
use crate::resolver::{ChannelConfig, Channels};
use crate::utils::Validator;

//
// Server configuration
//

/// Socket configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ListenConfig {
    listen: SocketAddr,
    enable_tls: bool,
    tls_key_file: Option<PathBuf>,
    tls_cert_file: Option<PathBuf>,
    tls_client_ca_file: Option<PathBuf>,
}

impl Default for ListenConfig {
    fn default() -> Self {
        Self {
            listen: SocketAddr::new(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)), 9080),
            enable_tls: false,
            tls_key_file: None,
            tls_cert_file: None,
            tls_client_ca_file: None,
        }
    }
}

impl Validator for ListenConfig {
    fn validate(&self) -> Result<(), ConfigError> {
        if self.enable_tls {
            self.tls_cert_file
                .as_deref()
                .map(Self::validate_filepath)
                .unwrap_or(Err(ConfigError::Message(
                    "File required for cert file".to_string(),
                )))?;
            self.tls_key_file
                .as_deref()
                .map(Self::validate_filepath)
                .unwrap_or(Err(ConfigError::Message(
                    "File required for key file".to_string(),
                )))?;
        }
        Ok(())
    }
}

/// Server configuration
#[derive(Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Server {
    /// The interface to listen to
    #[serde(flatten)]
    listen: ListenConfig,
    /// Number of workers
    num_workers: Option<usize>,
    /// Backend request timeout
    backend_request_timeout: u64,
    /// Shutdown grace period
    shutdown_timeout: u64,
    /// Handle Forwarded headers
    check_forwarded_headers: bool,
    /// CORS configuration
    pub cors: CorsConfig,
}

// For other server limits
// see https://docs.rs/actix-web/latest/actix_web/struct.HttpServer.html

const DEFAULT_SHUTDOWN_TIMEOUT_SECS: u64 = 30;

impl Default for Server {
    fn default() -> Self {
        Self {
            listen: ListenConfig::default(),
            num_workers: None,
            backend_request_timeout: ChannelConfig::default_timeout(),
            shutdown_timeout: DEFAULT_SHUTDOWN_TIMEOUT_SECS,
            check_forwarded_headers: true,
            cors: CorsConfig::default(),
        }
    }
}

impl Validator for Server {
    fn validate(&self) -> Result<(), ConfigError> {
        self.listen.validate()
    }
}

impl Server {
    pub fn num_workers(&self) -> usize {
        self.num_workers.unwrap_or_else(num_cpus::get_physical)
    }
    pub fn bind_address(&self) -> SocketAddr {
        self.listen.listen
    }
    pub fn request_timeout(&self) -> u64 {
        self.backend_request_timeout
    }
    pub fn shutdown_timeout(&self) -> u64 {
        self.shutdown_timeout
    }
    pub fn check_forwarded_headers(&self) -> bool {
        self.check_forwarded_headers
    }
}

//
// TLS configuration
//

use rustls::server::{ServerConfig as TlsServerConfig, WebPkiClientVerifier};
use rustls_pki_types::{CertificateDer, PrivateKeyDer, pem::PemObject};
use std::sync::Arc;

impl Server {
    pub fn tls_config(&self) -> Result<Option<TlsServerConfig>, ConfigError> {
        if !self.listen.enable_tls {
            return Ok(None);
        }
        // Existence is ensured by validation
        let cert_path = self.listen.tls_cert_file.as_ref().unwrap().as_path();
        let key_path = self.listen.tls_key_file.as_ref().unwrap().as_path();

        // Read server certificate

        let cert_chain = CertificateDer::pem_file_iter(cert_path)
            .map_err(|err| ConfigError::Message(format!("Server certificate error: {:?}", err)))?
            .map(|cert| {
                cert.map_err(|err| {
                    ConfigError::Message(format!("Server certificate error: {:?}", err))
                })
            })
            .collect::<Result<Vec<CertificateDer>, _>>()?;

        // Read server key

        let key = PrivateKeyDer::from_pem_file(key_path)
            .map_err(|err| ConfigError::Message(format!("Server tls key error: {:?}", err)))?;

        if let Some(ca_path) = self.listen.tls_client_ca_file.as_ref() {
            let mut store = rustls::RootCertStore::empty();

            fn error<E: std::error::Error>(err: E) -> ConfigError {
                ConfigError::Message(format!("Client certificate error {:?}", err))
            }

            //
            // Load client auth certificate
            //
            CertificateDer::pem_file_iter(ca_path)
                .map_err(error)?
                .try_for_each(|cert| match cert {
                    Ok(cert) => store.add(cert).map_err(error),
                    Err(err) => Err(error(err)),
                })?;

            let verifier = WebPkiClientVerifier::builder(Arc::new(store))
                .build()
                .map_err(error)?;

            TlsServerConfig::builder().with_client_cert_verifier(verifier)
        } else {
            TlsServerConfig::builder().with_no_client_auth()
        }
        .with_single_cert(cert_chain, key)
        .map_err(|err| ConfigError::Message(format!("TLS configuration error: {:}", err)))
        .map(Some)
    }
}

//
// Global settings
//
use config::{
    Config, ConfigError, Environment, FileFormat,
    builder::{ConfigBuilder, DefaultState},
};

/// Global settings
#[derive(Default, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub logging: Logging,
    pub server: Server,
    pub backends: Channels,
    /// The Monitor configuration
    #[cfg(feature = "monitor")]
    pub monitor: Option<qjazz_mon::Config>,
}

impl Settings {
    fn validate(mut self) -> Result<Self, ConfigError> {
        self.server.validate()?;
        self.backends.validate()?;

        // Set the server global request timeout value
        self.backends.timeout(self.server.request_timeout());

        Ok(self)
    }

    pub fn init_logger(&self) {
        self.logging.init()
    }

    fn builder() -> ConfigBuilder<DefaultState> {
        Config::builder().add_source(
            Environment::with_prefix("conf")
                .prefix_separator("_")
                .separator("__")
                .ignore_empty(true),
        )
    }

    /// Configure so environement will be as CONF_KEY__VALUE
    fn build(settings: ConfigBuilder<DefaultState>) -> Result<Self, ConfigError> {
        settings
            .build()?
            .try_deserialize()
            .and_then(|this: Self| this.validate())
    }

    fn error<T: Display>(msg: T) -> ConfigError {
        ConfigError::Message(format!("{}", msg))
    }

    /// Create from default and environment variables
    pub fn new() -> Result<Self, ConfigError> {
        Self::build(Self::builder())
    }

    /// Load configuration from env (Json)
    pub fn from_env<K: AsRef<OsStr>>(key: K) -> Result<Self, ConfigError> {
        match std::env::var(key) {
            Ok(content) => Self::build(
                Self::builder().add_source(config::File::from_str(&content, FileFormat::Json)),
            ),
            Err(std::env::VarError::NotPresent) => Self::new(),
            Err(err) => Err(Self::error(err)),
        }
    }

    /// Load configuration from file
    pub fn from_file(path: &Path) -> Result<Self, ConfigError> {
        Self::build(Self::builder().add_source(config::File::from(path)))
    }

    /// Load configuration with variable substitution
    pub fn from_file_template(path: &Path) -> Result<Self, ConfigError> {
        if let Some(loc) = path.parent() {
            let location = loc.canonicalize().map_err(Self::error)?;
            let replace =
                std::collections::BTreeMap::from([("location", location.to_string_lossy())]);
            let content =
                subst::substitute(&fs::read_to_string(path).map_err(Self::error)?, &replace)
                    .map_err(Self::error)?;
            Self::build(
                Self::builder().add_source(config::File::from_str(&content, FileFormat::Toml)),
            )
        } else {
            Self::from_file(path)
        }
    }
}
