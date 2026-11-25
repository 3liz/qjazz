//
// Adaptive scaling of the number of workers
//
// See ADAPTATIVE.md for the design.
//
use procfs::{Current, Meminfo};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::task::JoinHandle;
use tokio::time;
use tokio_util::sync::CancellationToken;

use qjazz_pool::Pool;
use qjazz_pool::stats::{Stats, WaitStats};

use crate::config::Scaling;

// Smoothing factor of the demand moving average
const SMOOTHING: f64 = 0.5;
// Number of consecutive samples above target required
// before scaling up
const SCALE_UP_SAMPLES: usize = 2;

/// A sample of the pool activity
#[derive(Debug, Clone, Copy)]
pub(crate) struct Sample {
    /// Nominal number of workers
    pub nominal: usize,
    pub min: usize,
    pub max: usize,
    /// Number of busy workers
    pub busy: usize,
    /// Number of requests waiting for a worker
    pub waiters: usize,
    /// Mean wait time for a worker since the previous sample
    pub mean_wait: Option<Duration>,
    /// Whether memory allows adding workers
    pub memory_ok: bool,
}

/// Scaling decision logic
///
/// Tracks an exponential moving average of the demand
/// (busy workers + waiting requests) and computes the number
/// of workers required to keep the utilization at `target`.
pub(crate) struct Controller {
    target: f64,
    cooldown: Duration,
    wait_threshold: Option<Duration>,
    demand: Option<f64>,
    above: usize,
    below_since: Option<Instant>,
}

impl Controller {
    pub fn new(conf: &Scaling) -> Self {
        Self {
            target: conf.target_utilization(),
            cooldown: conf.scale_down_cooldown(),
            wait_threshold: conf.wait_time_threshold(),
            demand: None,
            above: 0,
            below_since: None,
        }
    }

    /// Returns the smoothed demand
    pub fn demand(&self) -> Option<f64> {
        self.demand
    }

    // Reset the scaling state
    fn reset(&mut self) {
        self.above = 0;
        self.below_since = None;
    }

    /// Update with a new sample
    ///
    /// Returns the new nominal number of workers if it must be changed.
    pub fn update(&mut self, s: &Sample, now: Instant) -> Option<usize> {
        let inst = (s.busy + s.waiters) as f64;
        let demand = match self.demand {
            Some(d) => SMOOTHING * inst + (1. - SMOOTHING) * d,
            None => inst,
        };
        self.demand = Some(demand);

        if s.min >= s.max {
            // Scaling disabled
            self.reset();
            return None;
        }

        let mut desired = (demand / self.target).ceil() as usize;

        // Requests wait too long: add a worker anyway
        if let (Some(threshold), Some(wait)) = (self.wait_threshold, s.mean_wait)
            && wait > threshold
        {
            desired = desired.max(s.nominal + 1);
        }

        let desired = desired.max(s.min).min(s.max);

        match desired.cmp(&s.nominal) {
            std::cmp::Ordering::Greater => {
                self.below_since = None;
                self.above += 1;
                if self.above < SCALE_UP_SAMPLES {
                    None
                } else if !s.memory_ok {
                    log::warn!(
                        "Scaling: memory threshold reached, not adding workers \
                         (demand: {demand:.2}, desired: {desired})"
                    );
                    None
                } else {
                    self.above = 0;
                    Some(desired)
                }
            }
            std::cmp::Ordering::Less => {
                self.above = 0;
                let since = *self.below_since.get_or_insert(now);
                if now.duration_since(since) >= self.cooldown {
                    // Remove one worker at a time, then wait
                    // for another cooldown period.
                    self.below_since = Some(now);
                    Some(s.nominal - 1)
                } else {
                    None
                }
            }
            std::cmp::Ordering::Equal => {
                self.reset();
                None
            }
        }
    }
}

// Returns the fraction of used system memory
fn memory_usage() -> Option<f64> {
    let info = Meminfo::current().ok()?;
    let available = info.mem_available?;
    (info.mem_total > 0)
        .then(|| info.mem_total.saturating_sub(available) as f64 / info.mem_total as f64)
}

/// Start the scaling task
///
/// The task runs during the whole server lifetime but is
/// a no-op as long as `min_processes == max_processes`, so that
/// scaling may be enabled at runtime by patching the configuration.
pub(crate) fn handle_scaling(
    pool: Arc<Pool>,
    token: CancellationToken,
    conf: Scaling,
) -> JoinHandle<()> {
    tokio::spawn(async move {
        log::info!("Installing scaling handler");
        let mut controller = Controller::new(&conf);
        let mut prev_wait: WaitStats = pool.wait_stats();
        loop {
            tokio::select! {
                _ = token.cancelled() => { break; }
                _ = time::sleep(conf.interval()) => {}
            }

            let (min, max) = (pool.min_processes(), pool.max_processes());
            let stats = Stats::new(pool.as_ref());
            let wait = *stats.wait_stats();
            let sample = Sample {
                nominal: pool.num_processes(),
                min,
                max,
                busy: stats.active_workers(),
                waiters: stats.num_waiters(),
                mean_wait: wait.mean_since(&prev_wait),
                // Only read memory when relevant
                memory_ok: min >= max
                    || memory_usage().is_none_or(|used| used < conf.memory_threshold()),
            };
            prev_wait = wait;

            let Some(target) = controller.update(&sample, Instant::now()) else {
                continue;
            };

            log::info!(
                "Scaling workers: {} -> {target} (demand: {:.2}, waiters: {}, mean wait: {:?})",
                sample.nominal,
                controller.demand().unwrap_or(0.),
                sample.waiters,
                sample.mean_wait,
            );
            if let Err(err) = pool.set_num_processes(target).await {
                log::error!("Scaling failed: {err}, restoring {} workers", sample.nominal);
                if let Err(err) = pool.set_num_processes(sample.nominal).await {
                    log::error!("Failed to restore number of workers: {err}");
                }
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn conf() -> Scaling {
        serde_json::from_value(serde_json::json!({
            "target_utilization": 0.5,
            "scale_down_cooldown": 60,
            "wait_time_threshold": 500,
        }))
        .unwrap()
    }

    fn sample(nominal: usize, busy: usize, waiters: usize) -> Sample {
        Sample {
            nominal,
            min: 1,
            max: 4,
            busy,
            waiters,
            mean_wait: None,
            memory_ok: true,
        }
    }

    #[test]
    fn test_scale_up() {
        let mut c = Controller::new(&conf());
        let now = Instant::now();

        // 2 busy workers out of 2: demand 2 / 0.5 => 4 workers,
        // after two consecutive samples
        assert_eq!(c.update(&sample(2, 2, 0), now), None);
        assert_eq!(c.update(&sample(2, 2, 0), now), Some(4));

        // Bounded by max
        let mut c = Controller::new(&conf());
        let s = sample(2, 2, 5);
        assert_eq!(c.update(&s, now), None);
        assert_eq!(c.update(&s, now), Some(4));
    }

    #[test]
    fn test_scale_up_blocked_by_memory() {
        let mut c = Controller::new(&conf());
        let now = Instant::now();
        let s = Sample {
            memory_ok: false,
            ..sample(2, 2, 0)
        };
        assert_eq!(c.update(&s, now), None);
        assert_eq!(c.update(&s, now), None);
        // Memory available again
        assert_eq!(c.update(&sample(2, 2, 0), now), Some(4));
    }

    #[test]
    fn test_scale_up_on_wait_time() {
        // Low utilization but requests wait too long
        let mut c = Controller::new(&conf());
        let now = Instant::now();
        let s = Sample {
            mean_wait: Some(Duration::from_secs(1)),
            ..sample(2, 0, 0)
        };
        assert_eq!(c.update(&s, now), None);
        assert_eq!(c.update(&s, now), Some(3));
    }

    #[test]
    fn test_scale_down_with_cooldown() {
        let mut c = Controller::new(&conf());
        let t0 = Instant::now();
        let cooldown = Duration::from_secs(60);

        // Idle: desired is min (1)
        assert_eq!(c.update(&sample(4, 0, 0), t0), None);
        assert_eq!(c.update(&sample(4, 0, 0), t0 + cooldown / 2), None);
        // One worker removed after cooldown
        assert_eq!(c.update(&sample(4, 0, 0), t0 + cooldown), Some(3));
        // Then wait another cooldown period
        assert_eq!(c.update(&sample(3, 0, 0), t0 + cooldown + cooldown / 2), None);
        assert_eq!(c.update(&sample(3, 0, 0), t0 + cooldown * 2), Some(2));
    }

    #[test]
    fn test_activity_resets_cooldown() {
        let mut c = Controller::new(&conf());
        let t0 = Instant::now();
        let cooldown = Duration::from_secs(60);

        assert_eq!(c.update(&sample(2, 0, 0), t0), None);
        // Demand back to target: 1 busy / 0.5 => 2
        // (smoothed demand: 0.5 * 2 + 0.5 * 0 = 1)
        assert_eq!(c.update(&sample(2, 2, 0), t0 + cooldown / 2), None);
        // Low again: cooldown restarts
        assert_eq!(c.update(&sample(2, 0, 0), t0 + cooldown), None);
        assert_eq!(c.update(&sample(2, 0, 0), t0 + cooldown * 2), Some(1));
    }

    #[test]
    fn test_disabled() {
        let mut c = Controller::new(&conf());
        let now = Instant::now();
        let s = Sample {
            min: 2,
            max: 2,
            ..sample(2, 2, 10)
        };
        assert_eq!(c.update(&s, now), None);
        assert_eq!(c.update(&s, now), None);
        // Demand is still tracked
        assert!(c.demand().unwrap() > 0.);
    }
}
