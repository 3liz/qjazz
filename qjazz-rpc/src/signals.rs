//!
//! Handle signals
//!
//!
use signal_hook::consts::signal::{SIGCHLD, SIGINT, SIGTERM};
use signal_hook::iterator::{backend::Handle, Signals};
use std::error::Error;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use tokio::time;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;

use qjazz_pool::Pool;

// Run signal handling in its own thread

pub(crate) fn handle_signals(
    pool: Arc<RwLock<Pool>>,
    token: CancellationToken,
) -> Result<Handle, Box<dyn Error>> {
    let mut signals = Signals::new([SIGINT, SIGTERM, SIGCHLD])?;

    let handle = signals.handle();

    tokio::task::spawn_blocking(move || {
        log::debug!("Installing signal handler");

        let rescaling = Arc::new(AtomicBool::new(false));
        let throttle_duration = time::Duration::from_millis(200);
        
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
                    // Throttle rescaling so that when a child die we wait some 
                    // time for other child to die and so perform only one 
                    // rescaling task.
                    log::debug!("SIGCHLD detected");
                    if !rescaling.load(Ordering::Relaxed) {
                        rescaling.store(true, Ordering::Relaxed);
                        let mut throttle = time::interval(throttle_duration);
                        let pool = pool.clone();
                        let token = token.clone();
                        let state = rescaling.clone();
                        tokio::spawn(async move {
                            throttle.tick().await;
                            // Release barrier
                            state.store(false, Ordering::Relaxed);
                            if let Err(err) = pool.write().await.maintain_pool().await {
                                log::error!("Pool scaling failed: {:?}, terminating server", err);
                                token.cancel();
                            }
                        });
                    }
                }
                _ => {}
            }
        }
        log::trace!("Releasing signal handler");
        token.cancel();
    });
    Ok(handle)
}
