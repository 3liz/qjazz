use crate::errors::Error;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::path::PathBuf;
use std::sync::LazyLock;

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
                "{value} out of range {MIN}..{MAX}"
            )))
        }
    }
}

impl<const MIN: usize, const MAX: usize> BoundedUsize<MIN, MAX> {
    pub fn as_usize(&self) -> usize {
        self.0
    }
}

const LOG_CRITICAL: &str = "critical";
const LOG_ERROR: &str = "error";
const LOG_WARNING: &str = "warning";
const LOG_INFO: &str = "info";
const LOG_DEBUG: &str = "debug";
const LOG_TRACE: &str = "trace";

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
            value
                .as_str()
                .and_then(|value| match value.to_ascii_lowercase().as_str() {
                    "error" => Some(LOG_ERROR),
                    "warning" => Some(LOG_WARNING),
                    "info" => Some(LOG_INFO),
                    "debug" => Some(LOG_DEBUG),
                    "trace" => Some(LOG_TRACE),
                    "critical" => Some(LOG_CRITICAL),
                    _ => None,
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
    &PYTHON_EXEC
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
    ///
    /// This is the initial number of workers when the number
    /// of workers is adjusted dynamically between `min_processes`
    /// and `max_processes`.
    pub(crate) num_processes: BoundedUsize<1>,
    /// Lower bound of the number of workers.
    /// Defaults to `num_processes`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) min_processes: Option<BoundedUsize<1>>,
    /// Upper bound of the number of workers.
    /// Defaults to `num_processes`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) max_processes: Option<BoundedUsize<1>>,
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
    /// The maximum number of life cycles of a worker.
    /// Life cycles will be incremented on each QGIS
    /// request; when the count reaches
    /// this value, the worker is terminated and replaced
    /// by a fresh one.
    /// A value of 0 disables the limit
    pub max_life_cycles: usize,
}

impl Default for WorkerOptions {
    fn default() -> Self {
        Self {
            name: "".to_string(),
            num_processes: BoundedUsize(1),
            min_processes: None,
            max_processes: None,
            process_start_timeout: DEFAULT_START_TIMEOUT_SEC,
            cancel_timeout: DEFAULT_CANCEL_TIMEOUT_SEC,
            qgis: serde_json::json!({}),
            max_waiting_requests: BoundedUsize(DEFAULT_MAX_REQUESTS),
            max_chunk_size: BoundedUsize(DEFAULT_MAX_CHUNK_SIZE),
            restore_projects: Default::default(),
            max_life_cycles: 0,
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

    /// Lower bound of the number of workers
    pub fn min_processes(&self) -> usize {
        self.min_processes
            .map(|v| v.as_usize())
            .unwrap_or_else(|| self.num_processes())
    }

    /// Upper bound of the number of workers
    pub fn max_processes(&self) -> usize {
        self.max_processes
            .map(|v| v.as_usize())
            .unwrap_or_else(|| self.num_processes())
    }

    /// Validate options consistency
    ///
    /// Requires `min_processes <= num_processes <= max_processes`.
    pub fn validate(&self) -> Result<(), Error> {
        let (min, num, max) = (
            self.min_processes(),
            self.num_processes(),
            self.max_processes(),
        );
        // Unset bounds default to `num_processes`, so a failure
        // always involves an explicitly set bound.
        if num < min {
            Err(Error::InvalidConfiguration(format!(
                "num_processes ({num}) is lower than min_processes ({min})"
            )))
        } else if num > max {
            Err(Error::InvalidConfiguration(format!(
                "num_processes ({num}) is greater than max_processes ({max})"
            )))
        } else {
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn options(value: serde_json::Value) -> WorkerOptions {
        serde_json::from_value(value).unwrap()
    }

    #[test]
    fn test_processes_bounds() {
        // Bounds default to num_processes (fixed size pool)
        let opts = options(json!({ "num_processes": 3 }));
        assert_eq!(opts.min_processes(), 3);
        assert_eq!(opts.max_processes(), 3);
        assert!(opts.validate().is_ok());

        let opts = options(json!({ "num_processes": 2, "max_processes": 4 }));
        assert_eq!(opts.min_processes(), 2);
        assert_eq!(opts.max_processes(), 4);
        assert!(opts.validate().is_ok());

        let opts = options(json!({ "num_processes": 2, "min_processes": 3 }));
        assert!(opts.validate().is_err());

        let opts = options(json!({ "num_processes": 2, "max_processes": 1 }));
        assert!(opts.validate().is_err());

        // Unset bounds are not serialized
        let doc = serde_json::to_value(options(json!({}))).unwrap();
        assert!(doc.get("min_processes").is_none());
        assert!(doc.get("max_processes").is_none());
    }
}
