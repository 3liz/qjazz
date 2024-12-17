pub mod builder;
pub mod config;
pub mod errors;
pub mod messages;
pub mod pipes;
pub mod pool;
pub mod receiver;
pub mod rendezvous;
pub mod stats;
pub mod stream;
pub mod worker;

pub(crate) mod queue;

// reexport
pub use builder::Builder;
pub use errors::{Error, Result};
pub use pool::Pool;
pub use receiver::{Receiver, ScopedWorker};
pub use worker::Worker;
pub use config::WorkerOptions;

#[cfg(test)]
mod tests;
