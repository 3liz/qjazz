//!
//! Get stats for pool
//!
use crate::pool::Pool;
use std::ops::Deref;
use std::time::{Instant, SystemTime};

pub struct Stats {
    active: usize,
    idle: usize,
    dead: usize,
    failure_pressure: f64,
    request_pressure: f64,
    num_workers: usize,
    instant: Instant,
}

impl Stats {
    pub fn new<T: Deref<Target = Pool>>(pool: T) -> Self {
        let stats = pool.stats_raw();
        Self {
            active: stats.0,
            idle: stats.1,
            dead: stats.2,
            failure_pressure: pool.failure_pressure(),
            request_pressure: pool.num_waiters() as f64
                / pool.options().max_waiting_requests() as f64,
            num_workers: pool.num_workers(),
            instant: Instant::now(),
        }
    }

    pub fn num_workers(&self) -> usize {
        self.num_workers
    }

    pub fn request_pressure(&self) -> f64 {
        self.request_pressure
    }

    pub fn active_workers(&self) -> usize {
        self.active
    }
    pub fn idle_workers(&self) -> usize {
        self.idle
    }
    pub fn dead_workers(&self) -> usize {
        self.dead
    }

    /// Return the failure pressure as the ratio
    /// of number of dead processes over the number
    /// number of started processes.
    pub fn failure_pressure(&self) -> f64 {
        self.failure_pressure
    }

    /// Returns the measurement of the worker activity as
    /// `active / (active + idle)`.
    pub fn activity(&self) -> Option<f64> {
        let b = self.active + self.idle;
        if b > 0 {
            Some(self.active as f64 / b as f64)
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
