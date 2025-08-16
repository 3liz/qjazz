//! Rendez vous
//!
//! Allow synchronization with child process:
//! the rendez vous is used by child process to
//! notify `busy`/`ready` state.
//!
use nix::{errno::Errno, fcntl, fcntl::OFlag, sys::stat, unistd};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{self, AtomicBool};
use tempfile::TempDir;
use tokio::io::unix::AsyncFd;
use tokio::sync::Notify;
use tokio::task;

use crate::errors::{Error, Result};

/// Rendez-vous
///
/// The rendez-vous use named pipes (fifo) for communicating
/// with the child process.
///
/// Python client code example:
///
/// ```python
/// from pathlib import Path
/// from time import sleep
///
/// path = Path(os.environ["RENDEZ_VOUS"])
/// fp = path.open('wb')
///
/// # Set busy state
/// fp.write(b'\x01')
/// fp.flush()
///
/// # Do stuff
/// time.sleep(3)
///
/// # Set ready state
/// fp.write(b'\x00')
/// ```
pub struct RendezVous {
    tmp_dir: TempDir,
    path: PathBuf,
    handle: Option<task::JoinHandle<Result<()>>>,
    notify: Arc<Notify>,
    state: Arc<AtomicBool>,
}

impl Drop for RendezVous {
    fn drop(&mut self) {
        if let Some(handle) = &mut self.handle
            && !handle.is_finished()
        {
            handle.abort();
        }
    }
}

impl RendezVous {
    pub fn new() -> Result<Self> {
        let tmp_dir = TempDir::with_prefix("qjazz_")?;
        let path = tmp_dir.path().join("_rendez_vous");

        Ok(Self {
            tmp_dir,
            path,
            handle: None,
            notify: Arc::new(Notify::new()),
            // Start in BUSY state
            state: Arc::new(AtomicBool::new(true)),
        })
    }

    pub fn dir(&self) -> &Path {
        self.tmp_dir.path()
    }

    /// Return the path of the named pipe
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Check for ready state
    pub fn is_ready(&self) -> bool {
        !self.state.load(atomic::Ordering::Relaxed)
    }

    /// Wait for ready state
    pub async fn wait_ready(&self) {
        if !self.is_ready() {
            self.notify.notified().await
        }
    }

    /// Stop the listener and wait for its task
    /// completion
    pub async fn stop(&mut self) {
        if let Some(handle) = &mut self.handle
            && !handle.is_finished()
        {
            handle.abort();
            let _ = handle.await;
        }
    }

    /// Check if the listener is active
    pub fn is_running(&self) -> bool {
        if let Some(handle) = &self.handle {
            !handle.is_finished()
        } else {
            false
        }
    }

    /// Start the listener
    pub fn start(&mut self) -> Result<()> {
        if self.handle.is_some() {
            return Err(Error::Worker("Rendez-vous has been already started".into()));
        }

        // Open a named pipe and read continuously from it
        unistd::mkfifo(&self.path, stat::Mode::S_IRWXU)?;

        // Open file descriptor in non blocking mode
        let fd = AsyncFd::new(fcntl::open(
            &self.path,
            OFlag::O_RDONLY | OFlag::O_NONBLOCK,
            stat::Mode::S_IRWXU,
        )?)?;

        let notify = self.notify.clone();
        let state = self.state.clone();

        const MAX_EOF_RETURN: u16 = 10;

        let handle = tokio::spawn(async move {
            let mut buf = [1u8; 1];
            let mut eof = 0u16;
            loop {
                // XXX: If the other-side of the pipe
                // is closed then readable mode is always true
                // In order to detect such a case and discriminate
                // from incidental eof return, we check that *N* consecutive
                // no-data hits indicates that the client is no longer there.
                let mut guard = fd.readable().await?;
                match unistd::read(*guard.get_inner(), &mut buf) {
                    // NOTE Clear readiness if no data is read
                    Ok(0) => {
                        eof += 1;
                        if eof > MAX_EOF_RETURN {
                            // Set the BUSY state
                            state.store(true, atomic::Ordering::Relaxed);
                            log::error!("Too many EOF detected, client was probably closed");
                            return Err(Error::RendezVousDisconnected);
                        }
                        guard.clear_ready();
                    }
                    Ok(_) => match buf[0] {
                        0 => {
                            // READY
                            eof = 0;
                            log::trace!("Rendez-vous: READY");
                            state.store(false, atomic::Ordering::Relaxed);
                            notify.notify_waiters();
                        }
                        1 => {
                            // BUSY
                            eof = 0;
                            log::trace!("Rendez-vous: BUSY");
                            state.store(true, atomic::Ordering::Relaxed);
                        }
                        _ => {
                            log::error!("Rendez-vous received invalid value {buf:?}");
                        }
                    },
                    Err(Errno::EWOULDBLOCK) => {
                        eof = 0;
                        guard.clear_ready(); // Clear readiness
                        continue;
                    }
                    Err(errno) => {
                        log::error!("Rendez-vous I/O error: {errno:#?}");
                        return Err(Error::from(errno));
                    }
                }
            }
        });

        self.handle = Some(handle);
        Ok(())
    }
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tests::setup;
    use std::fs::File;
    use std::io::Write;

    #[tokio::test]
    async fn test_rendez_vous() {
        setup();
        let mut rdv = RendezVous::new().unwrap();

        assert!(rdv.dir().exists());

        // Start the rendez-vous
        rdv.start().unwrap();

        assert!(rdv.is_running());
        assert!(rdv.path().exists(), "{:?} does not exists", rdv.path);
        assert!(!rdv.is_ready());

        // meet at the rendez-vous
        let mut file = File::options().write(true).open(rdv.path()).unwrap();
        file.write(b"\x00").unwrap();
        file.flush().unwrap();

        rdv.wait_ready().await;

        assert!(rdv.is_ready());
        rdv.stop().await;
    }
}
