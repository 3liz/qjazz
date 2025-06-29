//! Qgis worker
use crate::config::{WorkerOptions, python_executable};
use crate::errors::{Error, Result};
use crate::messages::{self as msg, JsonValue, RequestMessage, RequestReply};
use crate::pipes::{Pipe, PipeOptions};
use crate::rendezvous::RendezVous;
use crate::stream::{ByteStream, ObjectStream};
use nix::sys::signal::{self, Signal};
use nix::unistd::Pid;
use std::fmt;
use std::process::Stdio;
use std::time::{Duration, Instant};
use tokio::process::{Child, Command};
use tokio::time::timeout;

// TODO: Make timeouts configurable
const TERM_TIMEOUT_SEC: u64 = 5;

// Child helper

struct _Child {
    child: Child,
    io: Pipe,
}

impl _Child {
    fn is_alive(&mut self) -> Result<bool> {
        self.child
            .try_wait()
            .map(|r| r.is_none())
            .map_err(Error::from)
    }
    fn send_signal(&mut self, sig: Signal) -> Result<i32> {
        // Not that the pid will be updated only if the task
        // has been waited somehow
        // So, sending signal without having been waiting
        // for it is UB
        let _ = self.is_alive()?; // Update the status
        match self.child.id() {
            Some(pid) => signal::kill(Pid::from_raw(pid as i32), sig)
                .map_err(Error::from)
                .map(|_| pid as i32),
            None => Err(Error::WorkerProcessDead),
        }
    }
}

/// Worker launcher
#[derive(Clone)]
pub struct WorkerLauncher {
    name: String,
    args: String,
    start_timeout: u64,
    cancel_timeout: u64,
    buffer_size: usize,
    qgis_options: String,
    log_level: &'static str,
}

impl WorkerLauncher {
    pub fn new(opts: &WorkerOptions, args: String, log_level: &'static str) -> Self {
        Self {
            args,
            name: opts.name.clone(),
            start_timeout: opts.process_start_timeout,
            cancel_timeout: opts.cancel_timeout,
            buffer_size: opts.max_chunk_size(),
            qgis_options: opts.qgis.to_string(),
            log_level,
        }
    }

    /// Start a worker and consume the launcher
    pub async fn spawn(self) -> Result<Worker> {
        let name = &self.name;
        let mut rendez_vous = RendezVous::new()?;

        let buffer_size = self.buffer_size;

        log::debug!("Starting child process");

        // Start rendez-vous
        rendez_vous.start()?;

        let mut child = Command::new(python_executable())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .args(self.args.split_whitespace())
            .arg(&self.name)
            .kill_on_drop(true)
            .env("CONF_LOGGING__LEVEL", self.log_level)
            .env("CONF_WORKER__QGIS", self.qgis_options)
            .env("CONF_WORKER__QGIS__MAX_CHUNK_SIZE", buffer_size.to_string())
            .env("RENDEZ_VOUS", rendez_vous.path())
            .spawn()?;

        let result;
        let start_timeout = self.start_timeout;
        let stdin = child.stdin.take().unwrap();
        let stdout = child.stdout.take().unwrap();

        // Wait for child to join the rendez-vous
        tokio::select! {
            v = timeout(
                Duration::from_secs(start_timeout),
                rendez_vous.wait_ready(),
            ) => if v.is_err() {
                // Timeout occured
                log::error!("Worker stalled at start, attempting to terminate");
                if let Err(err) = child.start_kill() {
                    let pid = child.id();
                    log::error!("Failed to kill process <{pid:?}>: {err:?}");
                }
                result = Err(Error::WorkerProcessFailure)
            } else {
                // Everything goes Ok
                let pipe = Pipe::new(stdin, stdout, PipeOptions { buffer_size });
                result = Ok(_Child { child, io: pipe })
            },
            v = child.wait() => {
                // Child exited prematurely
                result = v.map_err(Error::from).and_then(|exitstatus| {
                    log::error!("Worker exited prematurely <exitstatus: {exitstatus}");
                    Err(Error::WorkerProcessFailure)
                })
            }
        }

        let process = result?;
        let cancel_timeout = Duration::from_secs(self.cancel_timeout);

        Ok(Worker {
            name: name.into(),
            rendez_vous,
            cancel_timeout,
            ready_timeout: Duration::from_secs(1),
            process,
            uptime: Instant::now(),
            last_update: 0,
            generation: 1,
        })
    }
}

/// Worker
///
/// The worker object is a handle to the  child QGIS server process.
pub struct Worker {
    name: String,
    rendez_vous: RendezVous,
    cancel_timeout: Duration,
    ready_timeout: Duration,
    process: _Child,
    uptime: Instant,
    pub(crate) generation: usize,
    pub(crate) last_update: u64,
}

impl Worker {
    /// Terminate the child process
    ///
    /// Attempt a SIGTERM then wait for 5s before attempting a
    /// kill.
    pub async fn terminate(&mut self) -> Result<()> {
        if let Ok(Some(status)) = self.process.child.try_wait() {
            log::info!(
                "Worker terminated with exit status {:?}",
                status.code().unwrap_or(-1)
            );
        } else {
            log::debug!("Terminating worker {}", self.id());
            self.rendez_vous.stop().await;
            self.process.send_signal(Signal::SIGTERM)?;
            if timeout(
                Duration::from_secs(TERM_TIMEOUT_SEC),
                self.process.child.wait(),
            )
            .await
            .is_err()
            {
                log::warn!(
                    "Worker not {} (pid: {:?} terminated, kill forced...",
                    self.name,
                    self.process.child.id(),
                );
                self.process.child.start_kill().inspect_err(|err| {
                    log::error!("Failed to  kill worker [{:?}] {:?}", self.id(), err);
                })?;
            }
        }
        Ok(())
    }

    /// Check if the worker is ready to process messages
    pub fn is_ready(&self) -> bool {
        self.rendez_vous.is_ready()
    }

    /// Wait for the worker to be ready to process messages
    pub async fn wait_ready(&self) -> Result<()> {
        if !self.rendez_vous.is_running() {
            return Err(Error::RendezVousDisconnected);
        }
        self.rendez_vous.wait_ready().await;
        Ok(())
    }

    /// Return the name of the process
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Drain data until is not done
    pub(crate) async fn drain_until_task_done(&mut self) -> Result<()> {
        loop {
            // Drain the process
            let drained = self.io()?.drain().await.inspect_err(|err| {
                log::debug!("Drain failed [{}] {:?}", self.id(), err);
            })?;

            if self.rendez_vous.is_ready() {
                // Since rendez vous is ready, we expect
                // that all data pushed by the process
                // have been read
                break;
            }
            // Not ready yet; we may still expect some
            // data to retrieve.
            if !drained {
                // let some time to finish
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        }
        Ok(())
    }

    /// Cancel the task by sending a SIGHUP signal
    pub async fn cancel(&mut self) -> Result<()> {
        log::debug!(
            "Cancelling job {}:{:?}",
            &self.name,
            self.process.child.id(),
        );
        self.process.send_signal(signal::SIGHUP)?;
        // Pull output from current job.
        self.drain_until_task_done().await.inspect_err(|err| {
            log::debug!("Worker cancel error: {:?}", err);
        })
    }

    /// Attempt to cancel gracefully any pending job.
    ///
    /// If `done_hint` is set to `false`, then we assume that an
    /// incomplete response is still pending and leftover data will be drained
    /// from the process.
    ///
    /// If `done_hint` is set to `true`, we assume that a complete response
    /// has been received; if the worker reach ready state
    pub async fn cancel_timeout(&mut self, done_hint: bool) -> Result<()> {
        // Wait for readiness
        if let Ok(rv) = timeout(self.ready_timeout, self.wait_ready()).await {
            if rv.is_ok() && !done_hint {
                self.drain_until_task_done().await
            } else {
                rv
            }
        } else {
            match timeout(self.cancel_timeout, self.cancel()).await {
                Err(_) => Err(Error::WorkerStalled),
                Ok(rv) => rv,
            }
        }
    }

    /// Return the id of the Worker
    pub fn id(&self) -> WorkerId {
        WorkerId {
            value: self.process.child.id(),
        }
    }

    /// Returns the uptime for this worker
    pub fn uptime(&self) -> Duration {
        self.uptime.elapsed()
    }

    /// Return true if the worker is alive
    pub fn is_alive(&mut self) -> bool {
        self.process.is_alive().unwrap_or(false)
    }
}

//
// Message stubs
//

impl Worker {
    // Get the child process in safe way
    fn io(&mut self) -> Result<&mut Pipe> {
        if !self.process.is_alive()? {
            Err(Error::WorkerProcessDead)
        } else {
            Ok(&mut self.process.io)
        }
    }

    //
    // Miscellaneous
    //

    /// Send ping echo string
    pub async fn ping(&mut self, echo: &str) -> Result<String> {
        self.io()?
            .send_message(msg::PingMsg { echo })
            .await
            .map(|(_, s)| s)
    }

    /// Send sleep
    pub async fn sleep(&mut self, delay: i64) -> Result<()> {
        self.io()?
            .send_noreply_message(msg::SleepMsg { delay })
            .await
    }

    /// Return environment
    pub async fn get_env(&mut self) -> Result<JsonValue> {
        self.io()?
            .send_message(msg::GetEnvMsg)
            .await
            .map(|(_, s)| s)
    }

    //
    // Request
    //

    /// Send a request to the QGIS server
    ///
    /// Returns RequestReply.
    /// Data returned by a Request message is retrieved using
    /// the `byte_stream()` method.
    pub async fn request<M>(&mut self, msg: M) -> Result<RequestReply>
    where
        M: RequestMessage,
    {
        let io = self.io()?;
        let (_, resp) = io.send_message::<RequestReply>(msg).await?;
        Ok(resp)
    }

    /// Get a ByteStream from worker io
    pub fn byte_stream(&mut self) -> Result<ByteStream> {
        Ok(ByteStream::new(self.io()?))
    }

    // Collections

    pub async fn collections(
        &mut self,
        location: Option<&str>,
        resource: Option<&str>,
        range: std::ops::Range<i64>,
    ) -> Result<msg::CollectionsPage> {
        self.io()?
            .send_message(msg::CollectionsMsg {
                location,
                resource,
                start: range.start,
                end: range.end,
            })
            .await
            .map(|(_, resp)| resp)
    }

    //
    // Cache
    //

    /// Checkout project status
    pub async fn checkout_project(&mut self, uri: &str, pull: bool) -> Result<msg::CacheInfo> {
        self.io()?
            .send_message(msg::CheckoutProjectMsg { uri, pull })
            .await
            .map(|(_, resp)| resp)
    }

    /// Drop project from cache
    pub async fn drop_project(&mut self, uri: &str) -> Result<msg::CacheInfo> {
        self.io()?
            .send_message(msg::DropProjectMsg { uri })
            .await
            .map(|(_, resp)| resp)
    }

    /// Update all projects in cache
    ///
    /// Return a streamed list of cached object with their new status
    pub async fn update_cache(&mut self) -> Result<()> {
        self.io()?
            .send_message(msg::UpdateCacheMsg)
            .await
            .map(|(_, resp)| resp)
    }

    /// Clear all items in cache
    pub async fn clear_cache(&mut self) -> Result<()> {
        self.io()?
            .send_message(msg::ClearCacheMsg)
            .await
            .map(|(_, resp)| resp)
    }

    /// List all items in cache
    pub async fn list_cache(&mut self) -> Result<ObjectStream<msg::CacheInfo>> {
        let io = self.io()?;
        io.put_message(msg::ListCacheMsg.into()).await?;
        Ok(ObjectStream::new(io))
    }

    /// Returs all projects availables
    ///
    /// If `location` is set, returns only projects availables for
    /// this particular location
    pub async fn catalog(
        &mut self,
        location: Option<&str>,
    ) -> Result<ObjectStream<msg::CatalogItem>> {
        let io = self.io()?;
        io.put_message(msg::CatalogMsg { location }.into()).await?;
        Ok(ObjectStream::new(io))
    }

    /// Returns project information from loaded project in cache
    /// The method will NOT load the project in cache
    pub async fn project_info(&mut self, uri: &str) -> Result<msg::ProjectInfo> {
        self.io()?
            .send_message(msg::GetProjectInfoMsg { uri })
            .await
            .map(|(_, resp)| resp)
    }

    //
    // Plugins
    //

    /// List loaded plugins
    pub async fn list_plugins(&mut self) -> Result<ObjectStream<msg::PluginInfo>> {
        let io = self.io()?;
        io.put_message(msg::PluginsMsg.into()).await?;
        Ok(ObjectStream::new(io))
    }

    //
    // Config
    //

    /// Update worker configuration
    pub async fn put_config(&mut self, config: &JsonValue) -> Result<()> {
        self.io()?
            .send_message(msg::PutConfigMsg { config })
            .await
            .map(|(_, resp)| resp)
    }

    /// Retrieve worker configuration
    pub async fn get_config(&mut self) -> Result<JsonValue> {
        self.io()?
            .send_message(msg::GetConfigMsg {})
            .await
            .map(|(_, resp)| resp)
    }

    //
    // Report
    //
    pub async fn get_report(&mut self) -> Result<JsonValue> {
        self.io()?.read_response().await.map(|(_, resp)| resp)
    }
}

/// A object representing a displayable Pid
#[derive(Debug, Clone, Copy)]
pub struct WorkerId {
    pub value: Option<u32>,
}

impl fmt::Display for WorkerId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(v) = &self.value {
            write!(f, "{}", v)
        } else {
            write!(f, "<notset>")
        }
    }
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::builder::Builder;
    use crate::messages;
    use crate::tests::setup;

    async fn build_worker() -> Result<Worker> {
        Builder::new(crate::rootdir!("process.py"))
            .name("test")
            .process_start_timeout(5)
            .start()
            .await
    }

    #[tokio::test]
    async fn test_worker_builder() {
        setup();

        let mut w = build_worker().await.unwrap();

        let resp = w.ping("hello").await.unwrap();
        assert_eq!(resp, "hello");
    }

    #[tokio::test]
    async fn test_worker_drain() {
        setup();

        let mut w = build_worker().await.unwrap();
        w.io()
            .unwrap()
            .put_message(messages::PingMsg { echo: "hello" }.into())
            .await
            .unwrap();
        w.drain_until_task_done().await.unwrap();
        assert!(w.is_ready());
    }
}
