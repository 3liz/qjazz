use core::net::SocketAddr;
use serde::{Deserialize, Serialize};
use std::fmt::Display;
use std::net::{IpAddr, Ipv6Addr};
use std::path::Path;
use std::time::Duration;

use crate::logger::Logging;

//
// Server configuration
//

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ListenConfig {
    address: SocketAddr,
}

impl Default for ListenConfig {
    fn default() -> Self {
        Self {
            address: SocketAddr::new(IpAddr::V6(Ipv6Addr::new(0, 0, 0, 0, 0, 0, 0, 1)), 23456),
        }
    }
}

impl ListenConfig {
    /// Return the socker addresss from this configuration
    pub fn address(&self) -> SocketAddr {
        self.address
    }
}

/// Worker configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub(crate) struct Server {
    /// The interface to listen to
    pub listen: ListenConfig,
    /// Timeout for requests in seconds
    pub timeout: u64,
    /// The maximum amount of time to wait in seconds before
    /// closing connections. During this period,
    /// no new connections are allowed.
    pub shutdown_grace_period: u64,
}

impl Default for Server {
    fn default() -> Self {
        Self {
            listen: Default::default(),
            timeout: 20,
            shutdown_grace_period: 10,
        }
    }
}

impl Server {
    pub fn timeout(&self) -> Duration {
        Duration::from_secs(self.timeout)
    }
    pub fn shutdown_grace_period(&self) -> Duration {
        Duration::from_secs(self.shutdown_grace_period)
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

        s.try_deserialize()
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
                std::collections::HashMap::from([("location", location.to_string_lossy())]);
            let content = subst::substitute(
                &std::fs::read_to_string(path)
                    .map_err(|err| ConfigError::Message(format!("{}", err)))?,
                &replace,
            )
            .map_err(|err| ConfigError::Message(format!("{}", err)))?;
            Self::build(
                Config::builder().add_source(config::File::from_str(&content, FileFormat::Toml)),
            )
        } else {
            Self::from_file(path)
        }
    }
}
