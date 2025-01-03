//!
//! Handle signals
//!
//!
use signal_hook::consts::signal::{SIGCHLD, SIGINT, SIGTERM};
use signal_hook::iterator::{backend::Handle, Signals};
use std::error::Error;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;

use qjazz_pool::Pool;

use crate::config;

// Run signal handling in its own thread

pub(crate) fn handle_signals(
    pool: Arc<RwLock<Pool>>,
    token: CancellationToken,
    settings: &config::Server,
) -> Result<Handle, Box<dyn Error>> {
    let mut signals = Signals::new([SIGINT, SIGTERM, SIGCHLD])?;

    let handle = signals.handle();

    let max_failure_pressure = settings.max_failure_pressure();

    tokio::task::spawn_blocking(move || {
        log::debug!("Installing signal handler");
        for signal in signals.forever() {
            match signal {
                SIGINT => {
                    log::info!("Server interrupted");
                    break;
                }
                SIGTERM => {
                    log::info!("Server terminated");
                    break;
                }
                SIGCHLD => {
                    let pool = pool.clone();
                    let token = token.clone();
                    tokio::spawn(async move {
                        log::debug!("SIGCHLD detected: handling failure pressure");
                        if pool.read().await.failure_pressure() >= max_failure_pressure {
                            log::error!("Too many worker failures, terminating server...");
                            token.cancel();
                        }
                    });
                }
                _ => {}
            }
        }
        log::trace!("Releasing signal handler");
        token.cancel();
    });
    Ok(handle)
}
