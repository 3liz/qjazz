//! Builder
use crate::config::{get_log_level, python_executable, WorkerOptions};
use crate::errors::Result;
use crate::messages::JsonValue;
use crate::utils::json_merge;
use crate::Worker;
use std::ffi::OsStr;
use std::process::Stdio;
use tokio::process::Command;

/// Builder
pub struct Builder {
    pub(crate) opts: WorkerOptions,
    pub(crate) command: Command,
}

// Builder Clone
impl Clone for Builder {
    fn clone(&self) -> Self {
        let mut builder =
            Builder::from_options(self.command.as_std().get_args(), self.opts.clone());
        // Update arguments and envs
        for (k, v) in self.command.as_std().get_envs() {
            match v {
                Some(v) => builder.env(k, v),
                None => builder.env_remove(k),
            };
        }
        builder
    }
}

impl Builder {
    // Initialize a Command for process creation
    fn new_command(opts: &WorkerOptions) -> Command {
        let mut command = Command::new(python_executable());
        // Preinitialize command so may reuse it
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .env("CONF_LOGGING__LEVEL", get_log_level())
            .env("CONF_WORKER__QGIS", opts.qgis.to_string());
        command
    }

    /// Create new builder from args
    pub fn new<I, S>(args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        Self::from_options(args, Default::default())
    }

    /// Create a new Builder from options
    pub fn from_options<I, S>(args: I, opts: WorkerOptions) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        let mut command = Self::new_command(&opts);
        command.args(args);
        command.arg(&opts.name);
        Self { opts, command }
    }

    /// Start a worker with the given configuration
    pub async fn start(&mut self) -> Result<Worker> {
        Worker::spawn(&mut self.command, &self.opts).await
    }

    /// Patch configuration
    pub fn patch(&mut self, patch: &serde_json::Value) -> Result<()> {
        let mut doc = serde_json::to_value(&self.opts)?;
        json_merge(&mut doc, patch);

        self.opts = serde_json::from_value(doc)?;

        // Update environment
        self.command
            .env("CONF_LOGGING__LEVEL", get_log_level())
            .env("CONF_WORKER__QGIS", self.opts.qgis.to_string());
        Ok(())
    }

    /// Start a worker by consumming the builder
    pub async fn start_owned(mut self) -> Result<Worker> {
        Worker::spawn(&mut self.command, &self.opts).await
    }

    /// Return worker options
    pub(crate) fn options(&self) -> &WorkerOptions {
        &self.opts
    }

    pub fn env<K, V>(&mut self, key: K, val: V) -> &mut Self
    where
        K: AsRef<OsStr>,
        V: AsRef<OsStr>,
    {
        self.command.env(key, val);
        self
    }
    pub fn env_remove<K: AsRef<OsStr>>(&mut self, key: K) -> &mut Self {
        self.command.env_remove(key);
        self
    }
    pub fn envs<I, K, V>(&mut self, vars: I) -> &mut Self
    where
        I: IntoIterator<Item = (K, V)>,
        K: AsRef<OsStr>,
        V: AsRef<OsStr>,
    {
        self.command.envs(vars);
        self
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
    pub fn num_processes(&mut self, value: usize) -> &mut Self {
        self.opts.num_processes = value;
        self
    }
    /// Add project to load at startup
    pub fn project(&mut self, value: &str) -> &mut Self {
        self.command.arg(value);
        self
    }
    /// Add multiple projects to load at startup
    pub fn projects<I, S>(&mut self, projects: I) -> &mut Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        self.command.args(projects);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_builder_patch() {
        let mut builder = Builder::new(&[crate::rootdir!("process.py")]);
        builder
            .name("test")
            .process_start_timeout(5)
            .num_processes(1);

        assert_eq!(builder.opts.num_processes, 1);
        assert_eq!(
            builder.opts.qgis,
            json!({
                "max_chunk_size": builder.opts.max_chunk_size
            })
        );

        builder
            .patch(&json!({
                "num_processes": 3,
                "qgis": {
                    "max_projects": 25
                }
            }))
            .unwrap();

        assert_eq!(builder.opts.num_processes, 3);
        assert_eq!(
            builder.opts.qgis,
            json!({
                "max_chunk_size": builder.opts.max_chunk_size,
                "max_projects": 25
            })
        );
    }
}
