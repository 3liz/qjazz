//!
//! Get stats for pool
//!
use std::time::{Instant, SystemTime};

pub struct Stats {
    active: usize,
    idle: usize,
    dead: usize,
    instant: Instant,
}

impl Stats {
    pub(crate) fn from_raw_stats(stats: (usize, usize, usize), instant: Instant) -> Self {
        Self {
            active: stats.0,
            idle: stats.1,
            dead: stats.2,
            instant,
        }
    }

    pub fn active(&self) -> usize {
        self.active
    }
    pub fn idle(&self) -> usize {
        self.idle
    }
    pub fn dead(&self) -> usize {
        self.dead
    }

    pub fn base(&self) -> usize {
        self.idle + self.active + self.dead
    }

    /// Return the failure pressure as the ratio
    /// of number of dead processes over the number
    /// number of started processes.
    pub fn failure_pressure(&self) -> f64 {
        self.dead as f64 / self.base() as f64
    }

    /// Returns the measurement of the worker activity as
    /// `active / (active + idle)`.
    pub fn activity(&self) -> Option<f64> {
        let b = self.active + self.idle;
        if b > 0 {
            Some(self.idle as f64 / b as f64)
        } else {
            None
        }
    }

    /// Return a system time timestamp relative
    /// to the instant of the measurement
    pub fn timestamp(&self) -> Option<SystemTime> {
        SystemTime::now().checked_sub(self.instant.elapsed())
    }
}
