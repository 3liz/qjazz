//!
//! Abstraction layer and implementations for
//! monitoring qjazz requestsa
//!
//! The monitor pipe messages to a subprocess command.
//!

mod config;
mod errors;
mod listener;

pub use config::Config;
pub use errors::Error;
pub use listener::{Monitor, Sender};

#[cfg(test)]
mod tests;
