use core::net::SocketAddr;
use serde::{Deserialize, Serialize};
use std::fmt::Display;
use std::net::{IpAddr, Ipv6Addr};
use std::path::{Path, PathBuf};
use std::time::Duration;
use std::{fs, io};

use crate::logger::Logging;

//
// Server configuration
//

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ListenConfig {
    address: SocketAddr,
    enable_tls: bool,
    tls_key_file: Option<PathBuf>,
    tls_cert_file: Option<PathBuf>,
}

impl Default for ListenConfig {
    fn default() -> Self {
        Self {
            address: SocketAddr::new(IpAddr::V6(Ipv6Addr::new(0, 0, 0, 0, 0, 0, 0, 1)), 23456),
            enable_tls: false,
            tls_key_file: None,
            tls_cert_file: None,
        }
    }
}

impl ListenConfig {
    /// Return the socker addresss from this configuration
    pub fn address(&self) -> SocketAddr {
        self.address
    }
    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.enable_tls {
            check_file_exists(&self.tls_cert_file, "TLS cert file")
                .and_then(|_| check_file_exists(&self.tls_key_file, "TLS key file"))
        } else {
            Ok(())
        }
    }
}

/// Worker configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct Server {
    /// The interface to listen to
    listen: ListenConfig,
    /// Use admin services
    enable_admin_services: bool,
    /// Timeout for requests in seconds
    timeout: u64,
    /// The maximum amount of time to wait in seconds before
    /// closing connections. During this period,
    /// no new connections are allowed.
    shutdown_grace_period: u64,
    /// Interval in seconds between attempts to replace the
    /// the dead processes
    rescale_period: u64,
    /// The maximum failure pressure allowed before terminating
    /// server with unrecoverable error
    max_failure_pressure: f64,
}

impl Default for Server {
    fn default() -> Self {
        Self {
            listen: Default::default(),
            timeout: 20,
            shutdown_grace_period: 10,
            enable_admin_services: true,
            rescale_period: 10,
            max_failure_pressure: 1.0,
        }
    }
}

impl Server {
    pub fn validate(&self) -> Result<(), ConfigError> {
        self.listen.validate()
    }
    pub fn listen(&self) -> &ListenConfig {
        &self.listen
    }
    pub fn enable_admin_services(&self) -> bool {
        self.enable_admin_services
    }
    pub fn timeout(&self) -> Duration {
        Duration::from_secs(self.timeout)
    }
    pub fn shutdown_grace_period(&self) -> Duration {
        Duration::from_secs(self.shutdown_grace_period)
    }
    pub fn rescale_period(&self) -> Duration {
        Duration::from_secs(self.rescale_period)
    }
    pub fn enable_tls(&self) -> bool {
        self.listen.enable_tls
    }
    pub fn tls_key(&self) -> io::Result<String> {
        fs::read_to_string(self.listen.tls_key_file.as_ref().unwrap())
    }
    pub fn tls_cert(&self) -> io::Result<String> {
        fs::read_to_string(self.listen.tls_cert_file.as_ref().unwrap())
    }
    pub fn max_failure_pressure(&self) -> f64 {
        self.max_failure_pressure
    }
}

//
// Global settings
//
use config::{
    builder::{ConfigBuilder, DefaultState},
    Config, ConfigError, Environment, FileFormat,
};

#[derive(Default, Debug, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct Settings {
    pub logging: Logging,
    pub server: Server,
    pub worker: qjazz_pool::WorkerOptions,
}

impl Settings {
    fn validate(self) -> Result<Self, ConfigError> {
        self.server.validate()?;
        Ok(self)
    }

    pub(crate) fn init_logger(&self) {
        self.logging.init()
    }

    /// Configure so environement will be as CONF_KEY__VALUE
    fn build(settings: ConfigBuilder<DefaultState>) -> Result<Self, ConfigError> {
        let s = settings
            .add_source(
                Environment::with_prefix("conf")
                    .prefix_separator("_")
                    .separator("__")
                    .ignore_empty(true),
            )
            .build()?;

        s.try_deserialize().and_then(|this: Self| this.validate())
    }

    fn error<T: Display>(msg: T) -> ConfigError {
        ConfigError::Message(format!("{}", msg))
    }

    /// Create from default and environment variables
    pub fn new() -> Result<Self, ConfigError> {
        Self::build(Config::builder())
    }

    /// Load configuration from file
    pub fn from_file(path: &Path) -> Result<Self, ConfigError> {
        Self::build(Config::builder().add_source(config::File::from(path)))
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
                Config::builder().add_source(config::File::from_str(&content, FileFormat::Toml)),
            )
        } else {
            Self::from_file(path)
        }
    }

    /// Set log level from json configuration
    pub fn set_log_level(config: &serde_json::Value) {
        if let Some(level) = config
            .get("logging")
            .and_then(|v| v.get("level"))
            .and_then(|v| v.as_str())
        {
            log::set_max_level(match level.to_lowercase().as_str() {
                "error" => log::LevelFilter::Error,
                "warning" => log::LevelFilter::Warn,
                "info" => log::LevelFilter::Info,
                "debug" => log::LevelFilter::Debug,
                "trace" => log::LevelFilter::Trace,
                "critical" => log::LevelFilter::Off,
                invalid => {
                    log::error!("Invalid log level: '{}'", invalid);
                    log::max_level() // Returns the current level filter
                }
            });
            log::info!("Log level set to: {}", log::max_level());
        }
    }
}

// Utils
fn check_file_exists(path: &Option<PathBuf>, name: &str) -> Result<(), ConfigError> {
    match path {
        None => Err(ConfigError::Message(format!(
            "Path required for '{}'",
            name
        ))),
        Some(p) => {
            if !p.exists() {
                Err(ConfigError::Message(format!(
                    "File {} does not exists !",
                    p.to_string_lossy()
                )))
            } else {
                Ok(())
            }
        }
    }
}
