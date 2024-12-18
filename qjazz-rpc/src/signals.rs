//!
//! Handle signals
//!
//!
use signal_hook::consts::signal::{SIGINT, SIGTERM};
use signal_hook::iterator::{backend::Handle, Signals};
use std::error::Error;
use tokio_util::sync::CancellationToken;

// Run signal handling in its own thread

pub(crate) fn handle_signals(token: CancellationToken) -> Result<Handle, Box<dyn Error>> {
    let mut signals = Signals::new([SIGINT, SIGTERM])?;
    let handle = signals.handle();
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
                _ => {}
            }
        }
        log::trace!("Releasing signal handler");
        token.cancel();
    });
    Ok(handle)
}
