use serde::{Deserialize, Serialize};
use std::sync::LazyLock;
use std::fmt;
use std::path::PathBuf;
use crate::errors::Error;

#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(try_from = "usize")]
pub(crate) struct BoundedUsize<const MIN: usize, const MAX: usize = { usize::MAX }>(usize);

impl<const MIN: usize, const MAX: usize> fmt::Display for BoundedUsize<MIN, MAX> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl<const MIN: usize, const MAX: usize> TryFrom<usize> for BoundedUsize<MIN, MAX> {
    type Error = Error;

    fn try_from(value: usize) -> Result<Self, Self::Error> {
        if (MIN..=MAX).contains(&value) {
            Ok(Self(value))
        } else {
            Err(Error::InvalidConfigValue(format!(
                "{} out of range {}..{}",
                value, MIN, MAX
            )))
        }
    }
}

impl<const MIN: usize, const MAX: usize> BoundedUsize<MIN, MAX> {
    pub fn as_usize(&self) -> usize {
        self.0
    }
}

const LOG_CRITICAL: &'static str = "critical";
const LOG_ERROR: &'static str = "error";
const LOG_WARNING: &'static str = "warning";
const LOG_INFO: &'static str = "info";
const LOG_DEBUG: &'static str = "trace";
const LOG_TRACE: &'static str = "trace";


pub(crate) fn get_log_level() -> &'static str {
    match log::max_level() {
        log::LevelFilter::Error => LOG_ERROR,
        log::LevelFilter::Warn => LOG_WARNING,
        log::LevelFilter::Info => LOG_INFO,
        log::LevelFilter::Debug => LOG_DEBUG,
        log::LevelFilter::Trace => LOG_TRACE,
        log::LevelFilter::Off => LOG_CRITICAL,
    }
}

// Return log level from json configuration
pub(crate) fn log_level_from_json(opts: &serde_json::Value) -> Option<&'static str> {
    opts.get("logging").and_then(|value| {
        value.get("level").and_then(|value| {
            value.as_str().and_then(|value| {
                match value.to_ascii_lowercase().as_str() {
                    "error" => Some(LOG_ERROR),
                    "info" => Some(LOG_INFO),
                    "debug" => Some(LOG_DEBUG),
                    "trace" => Some(LOG_TRACE),
                    "critical" => Some(LOG_CRITICAL),
                    _ => None,
                }
            })
        })
    })
}



static PYTHON_EXEC: LazyLock<PathBuf> = LazyLock::new(|| {
    std::env::var_os("PYTHON_EXEC")
        .map(PathBuf::from)
        .unwrap_or("python3".into())
});


pub(crate) fn python_executable() -> &'static PathBuf {
    &*PYTHON_EXEC
}

const DEFAULT_START_TIMEOUT_SEC: u64 = 5;
const DEFAULT_CANCEL_TIMEOUT_SEC: u64 = 3;
const DEFAULT_MAX_REQUESTS: usize = 50;
const DEFAULT_MAX_CHUNK_SIZE: usize = 1024 * 1024; // 1Mo

/// Worker configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct WorkerOptions {
    /// Name of the worker instance
    pub name: String,
    /// Number of simultanous workers
    pub(crate) num_processes: BoundedUsize<1>,
    /// Timeout for starting child process
    pub process_start_timeout: u64,
    /// Qgis configuration (see python implementation for details)
    pub qgis: serde_json::Value,
    /// The grace period to apply on worker timeout
    /// when attempting to cancel the actual request
    /// This number should be kept small (a few seconds) since it
    /// will be used after the response timeout.
    pub cancel_timeout: u64,
    /// The maximum number of requests that can be
    /// queued. If the number of waiting requests reach the limit,
    /// the subsequent requests will be returned with a `service unavailable`
    /// error.
    pub(crate) max_waiting_requests: BoundedUsize<1>,
    /// Set the maximum chunk size for streamed responses.
    pub(crate) max_chunk_size: BoundedUsize<1024>,
    /// Projects to restore at startup
    pub restore_projects: Vec<String>,
}

impl Default for WorkerOptions {
    fn default() -> Self {
        Self {
            name: "".to_string(),
            num_processes: BoundedUsize(1),
            process_start_timeout: DEFAULT_START_TIMEOUT_SEC,
            cancel_timeout: DEFAULT_CANCEL_TIMEOUT_SEC,
            qgis: serde_json::json!({ "max_chunk_size": DEFAULT_MAX_CHUNK_SIZE }),
            max_waiting_requests: BoundedUsize(DEFAULT_MAX_REQUESTS),
            max_chunk_size: BoundedUsize(DEFAULT_MAX_CHUNK_SIZE),
            restore_projects: Default::default(),
        }
    }
}

impl WorkerOptions {
    pub fn max_chunk_size(&self) -> usize {
        self.max_chunk_size.as_usize()
    }

    pub fn max_waiting_requests(&self) -> usize {
        self.max_waiting_requests.as_usize()
    }

    pub fn num_processes(&self) -> usize {
        self.num_processes.as_usize()
    }
}
