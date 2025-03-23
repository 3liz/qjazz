use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Monitor configuration
#[derive(Default, Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Path to the executable
    pub command: PathBuf,
    /// Arguments to commands
    pub args: Vec<String>,
    /// The configuration of the executable module
    /// The configuration is passed as QJAZZ_MON_CONFIG
    /// environment variable
    pub tags: HashMap<String, String>,
    pub config: serde_json::Value,
}
