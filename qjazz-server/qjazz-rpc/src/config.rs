use core::net::SocketAddr;
use serde::{Deserialize, Serialize};
use std::fmt::Display;
use std::net::{IpAddr, Ipv4Addr};
use std::path::{Path, PathBuf};
use std::time::Duration;
use std::{ffi::OsStr, fs, io};

use crate::logger::Logging;

//
// Rpc server configuration
//

/// Socket configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ListenConfig {
    address: SocketAddr,
    enable_tls: bool,
    tls_key_file: Option<PathBuf>,
    tls_cert_file: Option<PathBuf>,
    tls_client_cafile: Option<PathBuf>,
}

impl Default for ListenConfig {
    fn default() -> Self {
        Self {
            address: SocketAddr::new(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)), 23456),
            enable_tls: false,
            tls_key_file: None,
            tls_cert_file: None,
            tls_client_cafile: None,
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

/// RPC Server configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Rpc {
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
    /// The maximum allowed failure pressure.
    /// If the failure pressure exceed this value then
    /// the service will exit with critical error condition
    max_failure_pressure: f64,
    /// Set memory high water mark as fraction of total memory.
    /// Workers are restarted if total memory percent usage of workers
    /// exceed that value.
    high_water_mark: f64,
    /// Interval in seconds between two check the out-of-memory
    /// handler.
    oom_period: u64,
}

impl Default for Rpc {
    fn default() -> Self {
        Self {
            listen: Default::default(),
            timeout: 20,
            shutdown_grace_period: 10,
            enable_admin_services: true,
            max_failure_pressure: 0.9,
            high_water_mark: 0.9,
            oom_period: 5,
        }
    }
}

impl Rpc {
    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.high_water_mark <= 0. || self.high_water_mark > 1. {
            return Err(ConfigError::Message(
                "'high_water_mark' value must be between 0 and 1".to_string(),
            ));
        }
        if self.oom_period < 3 {
            return Err(ConfigError::Message(
                "'oom_period' must be higher than 3s".to_string(),
            ));
        }
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
    pub fn max_failure_pressure(&self) -> f64 {
        self.max_failure_pressure
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
    pub fn tls_client_ca(&self) -> Option<io::Result<String>> {
        self.listen
            .tls_client_cafile
            .as_deref()
            .map(fs::read_to_string)
    }
    pub fn high_water_mark(&self) -> f64 {
        self.high_water_mark
    }
    pub fn oom_period(&self) -> Duration {
        Duration::from_secs(self.oom_period)
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
    pub rpc: Rpc,
    pub worker: qjazz_pool::WorkerOptions,
    #[cfg(feature = "monitor")]
    pub monitor: Option<qjazz_mon::Config>,
}

impl Settings {
    fn validate(self) -> Result<Self, ConfigError> {
        self.rpc.validate()?;
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
                .ignore_empty(true)
                .try_parsing(true) // Enable treating env as string list
                .list_separator(",")
                .with_list_parse_key("worker.restore_projects"),
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
