use anyhow::Context;
use core::net::SocketAddr;
use serde::{Deserialize, Serialize};
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
            let _ = self
                .tls_cert_file
                .as_deref()
                .map(Self::validate_filepath)
                .ok_or_else(|| ConfigError::Message("TLS: cert file required".to_string()))?;
            let _ = self
                .tls_key_file
                .as_deref()
                .map(Self::validate_filepath)
                .ok_or_else(|| ConfigError::Message("TLS: key file required".to_string()))?;
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
    pub fn tls_config(&self) -> anyhow::Result<Option<TlsServerConfig>> {
        if !self.listen.enable_tls {
            return Ok(None);
        }
        // Existence is ensured by validation
        let cert_path = self.listen.tls_cert_file.as_ref().unwrap().as_path();
        let key_path = self.listen.tls_key_file.as_ref().unwrap().as_path();

        // Read server certificate

        let cert_error_ctx = || format!("Server certificat error: {cert_path:?}");
        let cert_chain = CertificateDer::pem_file_iter(cert_path)
            .with_context(cert_error_ctx)?
            .collect::<Result<Vec<CertificateDer>, _>>()
            .with_context(cert_error_ctx)?;

        // Read server key

        let key = PrivateKeyDer::from_pem_file(key_path)
            .with_context(|| format!("Server tls key error: {key_path:?}"))?;

        if let Some(ca_path) = self.listen.tls_client_ca_file.as_ref() {
            let mut store = rustls::RootCertStore::empty();

            let error_ctx = || format!("Client certificate error {ca_path:?}");

            //
            // Load client auth certificate
            //
            CertificateDer::pem_file_iter(ca_path)
                .with_context(error_ctx)?
                .try_for_each(|cert| match cert {
                    Ok(cert) => store.add(cert),
                    Err(err) => Err(rustls::Error::General(err.to_string())),
                })
                .with_context(error_ctx)?;

            let verifier = WebPkiClientVerifier::builder(Arc::new(store))
                .build()
                .with_context(error_ctx)?;

            TlsServerConfig::builder().with_client_cert_verifier(verifier)
        } else {
            TlsServerConfig::builder().with_no_client_auth()
        }
        .with_single_cert(cert_chain, key)
        .map(Some)
        .context("TLS configuration error")
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

    /// Create from default and environment variables
    pub fn new() -> Result<Self, ConfigError> {
        Self::build(Self::builder())
    }

    /// Load configuration from env (Json)
    pub fn from_env<K: AsRef<OsStr>>(key: K) -> anyhow::Result<Self> {
        match std::env::var(key) {
            Ok(content) => Ok(Self::build(
                Self::builder().add_source(config::File::from_str(&content, FileFormat::Json)),
            )?),
            Err(std::env::VarError::NotPresent) => Ok(Self::new()?),
            Err(err) => Err(anyhow::anyhow!(err)),
        }
    }

    /// Load configuration from file
    pub fn from_file(path: &Path) -> Result<Self, ConfigError> {
        Self::build(Self::builder().add_source(config::File::from(path)))
    }

    /// Load configuration with variable substitution
    pub fn from_file_template(path: &Path) -> anyhow::Result<Self> {
        Ok(if let Some(loc) = path.parent() {
            let location = loc.canonicalize()?;
            let replace =
                std::collections::BTreeMap::from([("location", location.to_string_lossy())]);
            let content = subst::substitute(&fs::read_to_string(path)?, &replace)?;
            Self::build(
                Self::builder().add_source(config::File::from_str(&content, FileFormat::Toml)),
            )?
        } else {
            Self::from_file(path)?
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resolver::HeaderFilters;
    use serde_json::{Value, json};
    use std::sync::RwLock;

    // `Settings::builder()` always collects the process environment: hold this
    // lock while loading settings so that tests mutating the environment do not
    // race with the others.
    static ENV_LOCK: RwLock<()> = RwLock::new(());

    // Both the 'ring' and 'aws-lc-rs' backends are pulled in by the
    // dependency tree: rustls requires an explicit provider selection.
    //
    // ---> FIXED
    fn install_crypto_provider() {
        /*
        static ONCE: std::sync::Once = std::sync::Once::new();
        ONCE.call_once(|| {
            let _ = rustls::crypto::aws_lc_rs::default_provider().install_default();
        });
        */
    }

    fn config_path(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/configs")
            .join(name)
    }

    /// Load without variable substitution
    fn load(name: &str) -> Result<Settings, ConfigError> {
        let _guard = ENV_LOCK.read().unwrap_or_else(|e| e.into_inner());
        Settings::from_file(&config_path(name))
    }

    /// Load with '$location' substitution
    fn load_template(name: &str) -> anyhow::Result<Settings> {
        let _guard = ENV_LOCK.read().unwrap_or_else(|e| e.into_inner());
        Settings::from_file_template(&config_path(name))
    }

    fn error_of(name: &str) -> String {
        match load(name) {
            Ok(_) => panic!("Expected {name} to be rejected"),
            Err(err) => err.to_string(),
        }
    }

    fn template_error_of(name: &str) -> String {
        match load_template(name) {
            Ok(_) => panic!("Expected {name} to be rejected"),
            Err(err) => format!("{err:#}"),
        }
    }

    /// Serialized view of the settings: used to inspect fields that are
    /// private to the other modules.
    fn as_json(settings: &Settings) -> Value {
        serde_json::to_value(settings).unwrap()
    }

    fn channels(settings: Settings) -> std::collections::BTreeMap<String, ChannelConfig> {
        settings.backends.into_iter().collect()
    }

    //
    // Defaults
    //

    #[test]
    fn default_settings() {
        let settings = {
            let _guard = ENV_LOCK.read().unwrap_or_else(|e| e.into_inner());
            Settings::new().unwrap()
        };

        assert_eq!(
            settings.server.bind_address(),
            SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 9080),
        );
        assert_eq!(settings.server.num_workers(), num_cpus::get_physical());
        assert_eq!(settings.server.request_timeout(), 30);
        assert_eq!(settings.server.shutdown_timeout(), 30);
        assert!(settings.server.check_forwarded_headers());
        assert!(settings.server.tls_config().unwrap().is_none());
        assert!(!settings.backends.is_single_root_channel());
        assert_eq!(as_json(&settings)["logging"]["level"], json!("INFO"));
    }

    #[test]
    fn empty_config_file_yields_defaults() {
        let settings = load("defaults.toml").unwrap();
        let defaults = Settings::default();

        assert_eq!(
            settings.server.bind_address(),
            defaults.server.bind_address()
        );
        assert_eq!(
            settings.server.request_timeout(),
            defaults.server.request_timeout()
        );
        assert_eq!(
            settings.server.shutdown_timeout(),
            defaults.server.shutdown_timeout()
        );
        assert_eq!(as_json(&settings), as_json(&defaults));
    }

    #[test]
    fn default_backend_timeout_matches_channel_default() {
        assert_eq!(
            Settings::default().server.request_timeout(),
            ChannelConfig::default_timeout(),
        );
    }

    //
    // Full configuration
    //

    #[test]
    fn full_config_server_section() {
        let settings = load("full.toml").unwrap();

        assert_eq!(
            settings.server.bind_address(),
            "0.0.0.0:4000".parse::<SocketAddr>().unwrap(),
        );
        assert_eq!(settings.server.num_workers(), 4);
        assert_eq!(settings.server.request_timeout(), 15);
        assert_eq!(settings.server.shutdown_timeout(), 60);
        assert!(!settings.server.check_forwarded_headers());

        // TLS is off: no tls settings expected
        assert!(!settings.server.listen.enable_tls);
        assert!(settings.server.listen.tls_cert_file.is_none());
        assert!(settings.server.listen.tls_key_file.is_none());
        assert!(settings.server.listen.tls_client_ca_file.is_none());
        assert!(settings.server.tls_config().unwrap().is_none());

        assert_eq!(as_json(&settings)["logging"]["level"], json!("DEBUG"));
    }

    #[test]
    fn full_config_cors_section() {
        let settings = load("full.toml").unwrap();
        let cors = &as_json(&settings)["server"]["cors"];

        assert_eq!(cors["allowed_methods"], json!(["GET", "POST", "OPTIONS"]));
        assert_eq!(cors["allowed_headers"], json!(["x-custom-header"]));
        assert_eq!(
            cors["allowed_origins"],
            json!({"hosts": ["https://foo.example.com", "https://bar.example.com"]}),
        );
        assert_eq!(cors["max_age"], json!(3600));

        // The actix middleware must be buildable from that configuration
        let _ = settings.server.cors.configure();
    }

    #[test]
    fn full_config_backends() {
        let settings = load("full.toml").unwrap();
        assert!(!settings.backends.is_single_root_channel());

        let channels = channels(settings);
        // Channels are stored in a sorted map
        assert_eq!(channels.keys().collect::<Vec<_>>(), vec!["first", "second"]);

        let first = &channels["first"];
        assert_eq!(first.title, "First backend");
        assert_eq!(first.description, "The first test backend");
        assert_eq!(first.route, "/first");
        assert_eq!(first.service(), ("first.example.com", 23457));
        assert!(first.allow_direct_resolution);
        assert!(first.disable_root_catalog);
        assert!(!first.enable_tls());
        assert!(first.admin.enabled());
        assert!(!first.admin.undisclosed());

        assert_eq!(first.api.len(), 2);
        assert_eq!(first.api[0].endpoint, "features");
        assert_eq!(first.api[0].name, "WFS3");
        assert_eq!(first.api[0].description, "Features OGC Api");
        assert!(first.api[0].delegate);
        assert_eq!(first.api[1].endpoint, "lizmap");
        assert!(!first.api[1].delegate);
        assert_eq!(first.api[1].description, "");

        // Defaults applied to the second backend
        let second = &channels["second"];
        assert_eq!(second.route, "/second");
        // Default port
        assert_eq!(second.service(), ("second.example.com", 23456));
        assert!(!second.allow_direct_resolution);
        assert!(!second.disable_root_catalog);
        assert!(!second.admin.enabled());
        assert!(second.admin.undisclosed());
        assert!(second.api.is_empty());
    }

    #[test]
    fn forward_headers_filters() {
        let channels = channels(load("full.toml").unwrap());

        let filters = &channels["first"].forward_headers;
        // Prefix match
        assert!(filters.apply("x-qgis-user"));
        assert!(!filters.apply("qgis-user"));
        // Suffix match
        assert!(filters.apply("some-suffix"));
        // Plain match, case insensitive
        assert!(filters.apply("x-plain"));
        assert!(filters.apply("X-Plain"));
        assert!(!filters.apply("x-plain-not"));
        // Regex match
        assert!(filters.apply("x-re-value"));
        assert!(!filters.apply("unmatched"));

        // Default filters
        let filters = &channels["second"].forward_headers;
        assert!(filters.apply("x-qgis-user"));
        assert!(filters.apply("x-lizmap-user"));
        assert!(!filters.apply("x-other"));
        let _: &HeaderFilters = filters;
    }

    #[test]
    fn full_config_serialization_roundtrip() {
        let settings = load("full.toml").unwrap();
        let json = as_json(&settings);

        let restored: Settings = serde_json::from_value(json.clone()).unwrap();
        let restored = restored.validate().unwrap();

        assert_eq!(as_json(&restored), json);
    }

    //
    // Request timeouts
    //

    #[test]
    fn server_timeout_propagated_to_channels() {
        let settings = load("channel-timeouts.toml").unwrap();
        assert_eq!(settings.server.request_timeout(), 17);

        let channels = channels(settings);
        // Explicit channel timeout is kept
        assert_eq!(channels["with_timeout"].timeout().as_secs(), 3);
        // Missing channel timeout inherits the server value
        assert_eq!(channels["without_timeout"].timeout().as_secs(), 17);
    }

    #[test]
    fn full_config_timeouts() {
        let channels = channels(load("full.toml").unwrap());
        assert_eq!(channels["first"].timeout().as_secs(), 5);
        assert_eq!(channels["second"].timeout().as_secs(), 15);
    }

    //
    // Routes validation
    //

    #[test]
    fn single_root_channel() {
        let settings = load("single-root.toml").unwrap();
        assert!(settings.backends.is_single_root_channel());
    }

    #[test]
    fn root_route_rejected_with_multiple_backends() {
        let err = error_of("multiple-root-route.toml");
        assert!(err.contains("not allowed with multiple backends"));
    }

    #[test]
    fn route_without_leading_separator_rejected() {
        assert!(error_of("invalid-route.toml").contains("must starts with a '/'"));
    }

    #[test]
    fn api_endpoint_with_separator_rejected() {
        let err = error_of("invalid-api-endpoint.toml");
        assert!(err.contains("must not contains separator '/'"));
    }

    //
    // Deserialization errors
    //

    #[test]
    fn invalid_log_level_rejected() {
        let err = error_of("invalid-log-level.toml");
        assert!(err.contains("doesn't match an existing log level"));
    }

    #[test]
    fn invalid_listen_address_rejected() {
        assert!(error_of("invalid-listen.toml").contains("invalid socket address"));
    }

    #[test]
    fn unknown_field_rejected() {
        assert!(error_of("unknown-cors-field.toml").contains("allowed_verbs"));
    }

    #[test]
    fn missing_file_rejected() {
        let _guard = ENV_LOCK.read().unwrap_or_else(|e| e.into_inner());
        assert!(Settings::from_file(&config_path("no-such-file.toml")).is_err());
    }

    //
    // Server TLS
    //

    #[test]
    fn tls_enabled() {
        install_crypto_provider();
        let settings = load_template("tls-enabled.toml").unwrap();

        assert_eq!(
            settings.server.bind_address(),
            "127.0.0.1:8443".parse::<SocketAddr>().unwrap(),
        );
        assert!(settings.server.listen.enable_tls);
        assert!(
            settings
                .server
                .listen
                .tls_cert_file
                .as_deref()
                .is_some_and(Path::is_absolute)
        );
        assert!(settings.server.tls_config().unwrap().is_some());
    }

    #[test]
    fn tls_with_client_auth() {
        install_crypto_provider();
        let settings = load_template("tls-client-auth.toml").unwrap();
        assert!(settings.server.listen.tls_client_ca_file.is_some());
        assert!(settings.server.tls_config().unwrap().is_some());
    }

    #[test]
    fn tls_without_certificate_rejected() {
        assert!(template_error_of("tls-no-cert.toml").contains("cert file"));
    }

    #[test]
    fn tls_without_key_rejected() {
        assert!(template_error_of("tls-no-key.toml").contains("key file"));
    }

    #[test]
    fn tls_with_missing_certificate_file_rejected() {
        assert!(template_error_of("tls-missing-cert-file.toml").contains("missing.crt"));
    }

    //
    // Backend TLS
    //

    #[test]
    fn backend_tls_config() {
        let settings = load_template("backend-tls.toml").unwrap();
        let channels = channels(settings);

        let channel = &channels["secured"];
        assert!(channel.enable_tls());
        assert_eq!(channel.hostname(), "localhost");
        assert!(channel.tls_config().is_ok());
    }

    #[test]
    fn backend_tls_with_missing_cafile_rejected() {
        assert!(template_error_of("backend-tls-missing-cafile.toml").contains("missing.crt"));
    }

    #[test]
    fn backend_files_not_checked_when_tls_disabled() {
        let settings = load_template("backend-tls-disabled.toml").unwrap();
        let channels = channels(settings);

        let channel = &channels["plain"];
        assert!(!channel.enable_tls());
        // No tls config available for a plain channel
        assert!(channel.tls_config().is_err());
    }

    //
    // Template substitution
    //

    #[test]
    fn location_substituted_by_template_loader() {
        let settings = load_template("template.toml").unwrap();
        let cafile = as_json(&settings)["backends"]["test"]["cafile"]
            .as_str()
            .unwrap()
            .to_string();

        assert!(!cafile.contains("$location"));
        assert!(Path::new(&cafile).exists());
    }

    #[test]
    fn location_not_substituted_by_plain_loader() {
        let settings = load("template.toml").unwrap();
        assert_eq!(
            as_json(&settings)["backends"]["test"]["cafile"],
            json!("$location/../certs/localhost.crt"),
        );
    }

    //
    // Environment
    //

    #[test]
    fn from_env_falls_back_to_defaults_when_unset() {
        let _guard = ENV_LOCK.read().unwrap_or_else(|e| e.into_inner());
        let settings = Settings::from_env("QJAZZ_TEST_CONFIG_JSON_UNSET").unwrap();
        assert_eq!(as_json(&settings), as_json(&Settings::default()));
    }

    #[test]
    fn from_env_json_content() {
        const KEY: &str = "QJAZZ_TEST_CONFIG_JSON";

        let _guard = ENV_LOCK.write().unwrap_or_else(|e| e.into_inner());

        // SAFETY: the write lock ensures no other test reads the environment
        unsafe {
            std::env::set_var(
                KEY,
                r#"{
                    "server": {"listen": "127.0.0.1:5000", "shutdown_timeout": 12},
                    "backends": {"test": {"route": "/test", "host": "backend"}}
                }"#,
            )
        };

        let settings = Settings::from_env(KEY).unwrap();

        // SAFETY: see above
        unsafe { std::env::remove_var(KEY) };

        assert_eq!(
            settings.server.bind_address(),
            "127.0.0.1:5000".parse::<SocketAddr>().unwrap(),
        );
        assert_eq!(settings.server.shutdown_timeout(), 12);

        let channels = channels(settings);
        assert_eq!(channels["test"].route, "/test");
        assert_eq!(channels["test"].hostname(), "backend");
    }

    #[test]
    fn from_env_invalid_json() {
        const KEY: &str = "QJAZZ_TEST_CONFIG_INVALID_JSON";

        let _guard = ENV_LOCK.write().unwrap_or_else(|e| e.into_inner());

        // SAFETY: the write lock ensures no other test reads the environment
        unsafe { std::env::set_var(KEY, "{ not json }") };

        let result = Settings::from_env(KEY);

        // SAFETY: see above
        unsafe { std::env::remove_var(KEY) };

        assert!(result.is_err());
    }

    //
    // Monitor
    //

    #[test]
    #[cfg(feature = "monitor")]
    fn monitor_section() {
        let settings = load("monitor.toml").unwrap();
        let monitor = settings.monitor.as_ref().expect("Expecting monitor config");

        assert_eq!(monitor.command, PathBuf::from("python"));
        assert_eq!(monitor.args, ["monitor.py", "--verbose"]);
        assert_eq!(monitor.config, json!({"key": "value"}));
    }

    #[test]
    #[cfg(feature = "monitor")]
    fn no_monitor_section() {
        assert!(load("full.toml").unwrap().monitor.is_none());
    }

    #[test]
    #[cfg(not(feature = "monitor"))]
    fn monitor_section_ignored() {
        // The section is simply ignored when the feature is disabled
        assert!(load("monitor.toml").is_ok());
    }
}
