use serde::{Deserialize, Serialize};
use std::path::PathBuf;

pub(crate) fn get_log_level() -> &'static str {
    match log::max_level() {
        log::LevelFilter::Error => "error",
        log::LevelFilter::Warn => "warning",
        log::LevelFilter::Info => "info",
        log::LevelFilter::Debug => "debug",
        log::LevelFilter::Trace => "trace",
        log::LevelFilter::Off => "critical",
    }
}

pub(crate) fn python_executable() -> PathBuf {
    std::env::var_os("PYTHON_EXEC")
        .map(PathBuf::from)
        .unwrap_or("python3".into())
}

const DEFAULT_START_TIMEOUT_SEC: u64 = 5;
const DEFAULT_CANCEL_TIMEOUT_SEC: u64 = 3;
const DEFAULT_MAX_REQUESTS: usize = 50;
const DEFAULT_MAX_CHUNK_SIZE: usize = 1024 * 1024;

/// Worker configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct WorkerOptions {
    /// Name of the worker instance
    pub name: String,
    /// Number of simultanous workers
    pub num_processes: usize,
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
    pub max_waiting_requests: usize,
    /// Set the maximum chunk size for streamed responses.
    pub max_chunk_size: usize,
    /// Projects to restore at startup
    pub restore_projects: Vec<String>,
}

impl Default for WorkerOptions {
    fn default() -> Self {
        Self {
            name: "".to_string(),
            num_processes: 1,
            process_start_timeout: DEFAULT_START_TIMEOUT_SEC,
            cancel_timeout: DEFAULT_CANCEL_TIMEOUT_SEC,
            qgis: serde_json::json!({ "max_chunk_size": DEFAULT_MAX_CHUNK_SIZE }),
            max_waiting_requests: DEFAULT_MAX_REQUESTS,
            max_chunk_size: DEFAULT_MAX_CHUNK_SIZE,
            restore_projects: Default::default(),
        }
    }
}
