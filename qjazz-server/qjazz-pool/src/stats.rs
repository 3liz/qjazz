//!
//! Get stats for pool
//!
use crate::pool::Pool;
use std::ops::Deref;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime};

//
// Wait time
//

/// Cumulative counters of the time spent by requests
/// waiting for a worker.
#[derive(Default)]
pub(crate) struct WaitTimeRecorder {
    count: AtomicU64,
    total_us: AtomicU64,
    max_us: AtomicU64,
}

impl WaitTimeRecorder {
    pub fn record(&self, elapsed: Duration) {
        let us = u64::try_from(elapsed.as_micros()).unwrap_or(u64::MAX);
        self.total_us.fetch_add(us, Ordering::Relaxed);
        self.max_us.fetch_max(us, Ordering::Relaxed);
        self.count.fetch_add(1, Ordering::Relaxed);
    }

    pub fn snapshot(&self) -> WaitStats {
        // Counters are read independently: a snapshot taken
        // concurrently with a `record` may be slightly skewed,
        // which is acceptable for monitoring purposes.
        WaitStats {
            count: self.count.load(Ordering::Relaxed),
            total: Duration::from_micros(self.total_us.load(Ordering::Relaxed)),
            max: Duration::from_micros(self.max_us.load(Ordering::Relaxed)),
        }
    }
}

/// Snapshot of the cumulative time spent by requests
/// waiting for a worker since the pool was created.
///
/// Only requests that obtained a worker are accounted:
/// rejected or cancelled requests are not.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct WaitStats {
    /// Number of requests that obtained a worker
    pub count: u64,
    /// Cumulative wait time
    pub total: Duration,
    /// Longest wait time
    pub max: Duration,
}

impl WaitStats {
    /// Mean wait time since the pool was created
    pub fn mean(&self) -> Option<Duration> {
        Self::mean_of(self.count, self.total)
    }

    /// Mean wait time of the requests served between
    /// `prev` and `self`.
    ///
    /// Returns `None` if no request obtained a worker in
    /// that interval.
    pub fn mean_since(&self, prev: &WaitStats) -> Option<Duration> {
        Self::mean_of(
            self.count.saturating_sub(prev.count),
            self.total.saturating_sub(prev.total),
        )
    }

    fn mean_of(count: u64, total: Duration) -> Option<Duration> {
        (count > 0).then(|| {
            Duration::from_micros(
                u64::try_from(total.as_micros() / count as u128).unwrap_or(u64::MAX),
            )
        })
    }
}

//
// Pool stats
//

pub struct Stats {
    active: usize,
    idle: usize,
    failure_pressure: f64,
    request_pressure: f64,
    num_workers: usize,
    num_waiters: usize,
    wait_stats: WaitStats,
    instant: Instant,
}

impl Stats {
    pub fn new<T: Deref<Target = Pool>>(pool: T) -> Self {
        let (active, idle) = pool.stats_raw();
        Self {
            active,
            idle,
            failure_pressure: pool.failure_pressure(),
            request_pressure: pool.num_waiters() as f64
                / pool.options().max_waiting_requests() as f64,
            num_workers: pool.num_workers(),
            num_waiters: pool.num_waiters(),
            wait_stats: pool.wait_stats(),
            instant: Instant::now(),
        }
    }
    #[inline(always)]
    pub fn num_workers(&self) -> usize {
        self.num_workers
    }
    /// Number of requests waiting for a worker
    #[inline(always)]
    pub fn num_waiters(&self) -> usize {
        self.num_waiters
    }
    /// Cumulative wait time for a worker
    #[inline(always)]
    pub fn wait_stats(&self) -> &WaitStats {
        &self.wait_stats
    }
    #[inline(always)]
    pub fn request_pressure(&self) -> f64 {
        self.request_pressure
    }
    #[inline(always)]
    pub fn active_workers(&self) -> usize {
        self.active
    }
    #[inline(always)]
    pub fn idle_workers(&self) -> usize {
        self.idle
    }

    /// Return the failure pressure as the ratio
    /// of number of failed processes over the number
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wait_stats() {
        let rec = WaitTimeRecorder::default();
        assert_eq!(rec.snapshot().mean(), None);

        rec.record(Duration::from_millis(10));
        rec.record(Duration::from_millis(30));
        let prev = rec.snapshot();
        assert_eq!(prev.count, 2);
        assert_eq!(prev.mean(), Some(Duration::from_millis(20)));
        assert_eq!(prev.max, Duration::from_millis(30));

        // No request in the interval
        assert_eq!(rec.snapshot().mean_since(&prev), None);

        rec.record(Duration::from_millis(100));
        let next = rec.snapshot();
        assert_eq!(next.mean_since(&prev), Some(Duration::from_millis(100)));
        assert_eq!(next.mean(), Some(Duration::from_micros(46_666)));
        assert_eq!(next.max, Duration::from_millis(100));
    }
}
