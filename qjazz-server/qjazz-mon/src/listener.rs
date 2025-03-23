use serde::Serialize;
use std::io;
use std::process::Stdio;
//use std::time::{SystemTime, UNIX_EPOCH};
use tokio::io::AsyncWriteExt;
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::mpsc;
use tokio::time::{Duration, sleep};

use crate::config::Config;
use crate::errors::Error;

pub struct Monitor<T> {
    // Path of the executable
    command: Command,
    tx: mpsc::Sender<T>,
    rx: mpsc::Receiver<T>,
}

pub type Sender<T> = mpsc::Sender<T>;

impl<T: Serialize> Monitor<T> {
    pub fn new(conf: &Config) -> Self {
        let (tx, rx) = mpsc::channel(128);
        let mut command = Command::new(&conf.command);
        command
            .args(&conf.args)
            .env("QJAZZ_MON_CONFIG", conf.config.to_string());
        Self { command, tx, rx }
    }

    pub fn sender(&self) -> &Sender<T> {
        &self.tx
    }

    /// Consume messages
    pub async fn run(mut self) -> Result<impl Future<Output = Result<(), Error>>, Error> {
        let mut child = self.spawn().await?;
        let mut stdin = child.stdin.take().unwrap();

        #[inline]
        async fn send(stdin: &mut ChildStdin, buf: &[u8]) -> io::Result<()> {
            stdin.write_i32(buf.len() as i32).await?;
            stdin.write_all(buf).await
        }

        Ok(async move {
            log::info!("Starting monitor listener");
            let mut buf = Vec::new();
            loop {
                let msg = match self.rx.recv().await {
                    None => break,
                    Some(msg) => msg,
                };

                // Send data to child stdin
                if let Err(err) = {
                    buf.clear();
                    rmp_serde::encode::write_named(&mut buf, &msg)?;
                    send(&mut stdin, buf.as_slice()).await
                } {
                    // Check child status
                    match child.try_wait()? {
                        None => {
                            return Err(Error::from(err));
                        }
                        Some(status) => {
                            log::error!(
                                "Monitor process exited with status {status}, restarting..."
                            );
                            child = self.try_respawn().await?;
                            stdin = child.stdin.take().unwrap();
                        }
                    }
                }
            }
            log::info!("[Monitor] terminating listener");
            Ok(())
        })
    }

    async fn spawn(&mut self) -> io::Result<Child> {
        self.command
            .stdin(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
    }

    async fn try_respawn(&mut self) -> Result<Child, Error> {
        let respawn_delay = Duration::from_secs(60);
        let stabilize = Duration::from_secs(5);

        loop {
            let mut child = self.spawn().await?;
            // Wait for stability
            sleep(stabilize).await;
            match child.try_wait()? {
                None => break Ok(child),
                Some(st) => {
                    log::error!("Failed to restart monitor (code {st}), next attempt in 1 mn");
                    sleep(respawn_delay).await;
                }
            }
        }
    }
}
