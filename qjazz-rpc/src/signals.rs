//!
//! Handle signals
//!
//!
use tokio_util::sync::CancellationToken;
use signal_hook::consts::signal::{ SIGINT, SIGTERM };
use signal_hook::iterator::{Signals, backend::Handle};
use std::error::Error;

// Run signal handling in its own thread

pub (crate) fn handle_signals(token: CancellationToken) -> Result<Handle, Box<dyn Error>> {
    let mut signals = Signals::new(&[SIGINT, SIGTERM])?;  
    let handle = signals.handle();
    tokio::task::spawn_blocking(move || {
        log::info!("Installing signal handler");
        for signal in signals.forever() {
            match signal {
                SIGINT => {
                    log::info!("Server interrupted");
                    break;
                }
                SIGTERM => {
                    log::info!("Server terminated");
                    break
                }
                _ => {}
            }
        }
        log::debug!("Releasing signal handler");
        token.cancel();
    });
    Ok(handle)
}
