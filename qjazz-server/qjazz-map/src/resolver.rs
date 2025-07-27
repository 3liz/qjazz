//!
//! Channel
//!
use config::ConfigError;
use regex::{Regex, RegexBuilder};
use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use std::collections::{BTreeMap, btree_map};
use std::path::PathBuf;
use std::time::Duration;
use std::{fmt, fs, io};
use tonic::transport::{Certificate, ClientTlsConfig, Identity};

use crate::utils::Validator;

/// Channel host configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ChannelService {
    /// Hostname
    host: String,
    /// Port
    port: u16,
    /// Enable TLS
    enable_tls: bool,
    /// CA certificate
    cafile: Option<PathBuf>,
    /// Client authentification key
    client_key_file: Option<PathBuf>,
    /// Client authentification certificat
    client_cert_file: Option<PathBuf>,
}

impl Validator for ChannelService {
    fn validate(&self) -> Result<(), ConfigError> {
        if self.enable_tls {
            self.cafile
                .as_deref()
                .map_or(Ok(()), Self::validate_filepath)?;
            self.client_key_file
                .as_deref()
                .map_or(Ok(()), Self::validate_filepath)?;
            self.client_cert_file
                .as_deref()
                .map_or(Ok(()), Self::validate_filepath)?;
        }
        Ok(())
    }
}

const DEFAULT_CHANNEL_PORT: u16 = 23456;

impl Default for ChannelService {
    fn default() -> Self {
        Self {
            // NOTE localhost resolve to ipv4 as first ip
            host: "localhost".into(),
            port: DEFAULT_CHANNEL_PORT,
            enable_tls: false,
            cafile: None,
            client_key_file: None,
            client_cert_file: None,
        }
    }
}

/// Headers predicate
#[derive(Debug, Clone)]
pub enum HeaderFilter {
    Plain(String),
    Prefix(String),
    Suffix(String),
    Regex(Regex),
}

impl Serialize for HeaderFilter {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match self {
            Self::Plain(s) => s.serialize(serializer),
            Self::Prefix(s) => format!("{s}*").serialize(serializer),
            Self::Suffix(s) => format!("*{s}").serialize(serializer),
            Self::Regex(r) => format!("{r}").serialize(serializer),
        }
    }
}

impl<'de> Deserialize<'de> for HeaderFilter {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct Visitor;

        impl de::Visitor<'_> for Visitor {
            type Value = HeaderFilter;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("Expecting string pattern expression")
            }

            fn visit_str<E>(self, v: &str) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                if v.starts_with("re:") {
                    Ok(HeaderFilter::Regex(
                        RegexBuilder::new(v.trim_start_matches("re:"))
                            .case_insensitive(true)
                            .build()
                            .map_err(|e| {
                                log::error!("Invalid regular expression: {e:?}");
                                de::Error::invalid_value(de::Unexpected::Str(v), &self)
                            })?,
                    ))
                } else if v.starts_with('*') {
                    Ok(HeaderFilter::Suffix(
                        v.trim_start_matches('*').to_lowercase(),
                    ))
                } else if v.ends_with('*') {
                    Ok(HeaderFilter::Prefix(v.trim_end_matches('*').to_lowercase()))
                } else {
                    Ok(HeaderFilter::Plain(v.to_lowercase()))
                }
            }
        }

        deserializer.deserialize_str(Visitor)
    }
}

impl HeaderFilter {
    pub fn apply(&self, k: &str) -> bool {
        match self {
            Self::Plain(s) => k.eq_ignore_ascii_case(s),
            Self::Prefix(s) => k.starts_with(s),
            Self::Suffix(s) => k.ends_with(s),
            Self::Regex(r) => r.is_match(k),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct HeaderFilters(Vec<HeaderFilter>);

impl Default for HeaderFilters {
    fn default() -> Self {
        Self(vec![
            HeaderFilter::Prefix("x-qgis-".into()),
            HeaderFilter::Prefix("x-lizmap-".into()),
        ])
    }
}

impl HeaderFilters {
    pub fn apply(&self, k: &str) -> bool {
        self.0.iter().any(|p| p.apply(k))
    }
}

/// Backend channel service configuration
#[derive(Default, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ChannelConfig {
    /// Connection to service parameters
    #[serde(flatten)]
    service: ChannelService,
    /// A descriptive title
    pub title: String,
    /// Description of the service
    pub description: String,
    /// Route to service
    pub route: String,
    /// Set the headers that will be forwarded to the backend services.
    /// This may be useful if you have plugins that may deal with request headers
    ///
    /// Headers are compared using the following rules:
    /// - Plain name comparison
    /// - Suffix match if starting with '*'
    /// - Prefix match if ending with '*'
    /// - Regex match if prefixed with 're:'
    pub forward_headers: HeaderFilters,
    /// Allow sending direct project path to backend service.
    /// This requires that the backend service allow for direct resolution.
    pub allow_direct_resolution: bool,
    /// Api endpoints
    pub api: Vec<ApiEndPoint>,
    /// Disable root catalog api
    /// Requesting the catalog root will return
    /// 403 HTTP response with an informative message that the
    /// catalog has been disabled for the channel.
    pub disable_root_catalog: bool,
    /// Channel request timeout
    timeout: Option<u64>,
}

impl Validator for ChannelConfig {
    fn validate(&self) -> Result<(), ConfigError> {
        self.service.validate()?;

        if !self.route.starts_with("/") {
            return Err(ConfigError::Message(format!(
                "Path {} must starts with a '/'",
                self.route,
            )));
        }

        Ok(())
    }
}

const PROBE_INTERVAL: u64 = 5;

// NOTE: Backend usually have a response timeout set
// See qjazz_rpc for details
const DEFAULT_REQUEST_TIMEOUT_SECS: u64 = 30;

impl ChannelConfig {
    pub fn default_timeout() -> u64 {
        DEFAULT_REQUEST_TIMEOUT_SECS
    }

    pub fn service(&self) -> (&str, u16) {
        (self.hostname(), self.service.port)
    }
    pub fn hostname(&self) -> &str {
        self.service.host.as_str()
    }
    pub fn enable_tls(&self) -> bool {
        self.service.enable_tls
    }
    pub fn tls_config(&self) -> io::Result<ClientTlsConfig> {
        if !self.service.enable_tls {
            return Err(io::Error::other("TLS not enabled"));
        }

        let mut tls = ClientTlsConfig::new().domain_name(self.hostname());

        if let Some(cafile) = self.service.cafile.as_deref() {
            tls = tls.ca_certificate(Certificate::from_pem(fs::read_to_string(cafile)?));
        }

        if self.service.client_cert_file.is_some() {
            let cert = self
                .service
                .client_cert_file
                .as_deref()
                .map(fs::read_to_string)
                .unwrap()?;
            let key = self
                .service
                .client_key_file
                .as_deref()
                .map(fs::read_to_string)
                .unwrap()?;

            tls = tls.identity(Identity::from_pem(cert, key));
        }

        Ok(tls)
    }
    pub fn probe_interval(&self) -> Duration {
        Duration::from_secs(PROBE_INTERVAL)
    }
    pub fn timeout(&self) -> Duration {
        Duration::from_secs(self.timeout.unwrap_or(DEFAULT_REQUEST_TIMEOUT_SECS))
    }
}

/// Api endpoint
#[derive(Default, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ApiEndPoint {
    /// Api endpoint
    pub endpoint: String,
    /// Api name to delegate to
    ///
    /// Api delegation allow for using a baseurl different
    /// from the expected rootpath of qgis server api.
    /// For exemple, wfs3 request may be mapped to a completely different
    /// root path.
    pub delegate: bool,
    /// Descriptive name
    pub name: String,
    /// Api description
    pub description: String,
}

impl Validator for ApiEndPoint {
    fn validate(&self) -> Result<(), ConfigError> {
        if self.endpoint.contains("/") {
            Err(ConfigError::Message(
                "Api endpoint must not contains separator '/'".to_string(),
            ))
        } else {
            Ok(())
        }
    }
}

// Channel is B-tree map, this means that paths are
// sorted to shortest to longest for paths with the
// same prefix.
#[derive(Default, Debug, Serialize, Deserialize)]
#[serde(default)]
pub struct Channels(BTreeMap<String, ChannelConfig>);

impl Validator for Channels {
    fn validate(&self) -> Result<(), ConfigError> {
        if self.0.len() > 1 {
            return self.0.iter().try_for_each(|(_, c)| {
                if c.route == "/" {
                    Err(ConfigError::Message(
                        "Route '/' is not allowed with multiple backends".to_string(),
                    ))
                } else {
                    Ok(())
                }
            });
        }
        Ok(())
    }
}

impl Channels {
    // Check if we have a single backend  which route as "/"
    pub fn is_single_root_channel(&self) -> bool {
        self.0.len() == 1 && self.0.first_key_value().unwrap().1.route == "/"
    }
    // Set timeout if not already set on per config basis
    pub fn timeout(&mut self, timeout: u64) {
        self.0.iter_mut().for_each(|(_, cfg)| {
            if cfg.timeout.is_none() {
                cfg.timeout = Some(timeout);
            }
        });
    }
}

impl IntoIterator for Channels {
    type Item = (String, ChannelConfig);
    type IntoIter = btree_map::IntoIter<String, ChannelConfig>;

    fn into_iter(self) -> Self::IntoIter {
        self.0.into_iter()
    }
}
