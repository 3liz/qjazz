//! Builder
use crate::config::{WorkerOptions, get_log_level, log_level_from_json};
use crate::errors::Result;
use crate::messages::JsonValue;
use crate::utils::json_merge;
use crate::worker::{Worker, WorkerLauncher};

/// Builder
pub struct Builder {
    pub(crate) args: String,
    pub(crate) opts: WorkerOptions,
    pub(crate) log_level: &'static str,
}

impl Builder {
    /// Create new builder from args
    pub fn new(args: String) -> Self {
        Self::from_options(args, Default::default())
    }

    /// Create a new Builder from options
    pub fn from_options(args: String, opts: WorkerOptions) -> Self {
        Self {
            args,
            opts,
            log_level: get_log_level(),
        }
    }

    pub fn launcher(&self) -> WorkerLauncher {
        WorkerLauncher::new(&self.opts, self.args.clone(), self.log_level)
    }

    /// Start a worker with the given configuration
    pub async fn start(&mut self) -> Result<Worker> {
        self.launcher().spawn().await
    }

    /// Patch configuration
    pub fn patch(&mut self, patch: &serde_json::Value) -> Result<()> {
        if let Some(level) = log_level_from_json(patch) {
            self.log_level = level;
        }

        if let Some(patch) = patch.get("worker") {
            let mut doc = serde_json::to_value(&self.opts)?;
            json_merge(&mut doc, patch);
            self.opts = serde_json::from_value(doc)?;
        }

        Ok(())
    }

    /// Return worker options
    pub(crate) fn options(&self) -> &WorkerOptions {
        &self.opts
    }

    /// Return mutable worker options
    pub(crate) fn options_mut(&mut self) -> &mut WorkerOptions {
        &mut self.opts
    }

    pub fn name(&mut self, value: &str) -> &mut Self {
        self.opts.name = value.to_string();
        self
    }
    pub fn process_start_timeout(&mut self, value: u64) -> &mut Self {
        self.opts.process_start_timeout = value;
        self
    }
    pub fn process_config(&mut self, value: JsonValue) -> &mut Self {
        self.opts.qgis = value;
        self
    }
    pub fn num_processes(&mut self, value: usize) -> Result<&mut Self> {
        self.opts.num_processes = value.try_into()?;
        Ok(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_builder_patch() {
        let mut builder = Builder::new(crate::rootdir!("process.py"));
        let _ = builder
            .name("test")
            .process_start_timeout(5)
            .num_processes(1)
            .unwrap();

        assert_eq!(builder.opts.num_processes.as_usize(), 1);
        assert_eq!(
            builder.opts.qgis,
            json!({
                "max_chunk_size": builder.opts.max_chunk_size
            })
        );

        builder
            .patch(&json!({
                "worker": {
                    "num_processes": 3,
                    "qgis": {
                        "max_projects": 25
                    }
                }
            }))
            .unwrap();

        assert_eq!(builder.opts.num_processes.as_usize(), 3);
        assert_eq!(
            builder.opts.qgis,
            json!({
                "max_chunk_size": builder.opts.max_chunk_size,
                "max_projects": 25
            })
        );
    }
}
