//!
//! Worker pool
//!
//! Manage multiple workers
//!
use crate::builder::Builder;
use crate::config::WorkerOptions;
use crate::errors::{Error, Result};
use crate::queue::Queue;
use crate::restore::Restore;
use crate::stats::{WaitStats, WaitTimeRecorder};
use crate::worker::{Worker, WorkerId};
use futures::future::try_join_all;
use std::cmp;
use std::collections::HashSet;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::{Duration, Instant};
use tokio::sync::{Mutex, RwLock};

pub(crate) struct WorkerQueue {
    q: Queue<Worker>,
    // The actual number of living workers
    num_workers: AtomicUsize,
    // Nominal number of workers, bounded
    // by `min_processes..=max_processes`
    nominal: AtomicUsize,
    max_waiters: AtomicUsize,
    // Maximum life cycles of a worker (0: unlimited)
    max_life_cycles: AtomicUsize,
    // Number of requests waiting for a worker
    waiters: AtomicUsize,
    // Time spent by requests waiting for a worker
    wait_time: WaitTimeRecorder,
    generation: AtomicUsize,
    // Count worker's failure
    // A failure is when a worker cannot be properly
    // updated (errors while loading projects)
    // or properly terminated (stalled workers)
    failures: AtomicUsize,
    restore: RwLock<Restore>,
    // Keep a list of busy worker's pid
    // used for checking processe's resources
    // of busy workers.
    pids: RwLock<HashSet<u32>>,
}

impl WorkerQueue {
    pub fn max_waiters(&self) -> usize {
        self.max_waiters.load(Ordering::Relaxed)
    }

    pub fn num_waiters(&self) -> usize {
        self.waiters.load(Ordering::Relaxed)
    }

    fn set_max_waiters(&self, max_waiting_requests: usize) {
        self.max_waiters
            .store(max_waiting_requests, Ordering::Relaxed);
    }

    fn set_max_life_cycles(&self, value: usize) {
        self.max_life_cycles.store(value, Ordering::Relaxed);
    }

    // Returns true if the worker has reached its maximum
    // number of life cycles
    fn life_cycles_exhausted(&self, worker: &Worker) -> bool {
        let max_life_cycles = self.max_life_cycles.load(Ordering::Relaxed);
        max_life_cycles > 0 && worker.life_cycles() >= max_life_cycles
    }

    pub fn generation(&self) -> usize {
        self.generation.load(Ordering::Relaxed)
    }

    pub fn next_generation(&self) -> usize {
        self.generation.fetch_add(1, Ordering::Relaxed)
    }

    pub async fn remember_pid(&self, id: WorkerId) {
        if let Some(pid) = id.value {
            self.pids.write().await.insert(pid);
        }
    }

    async fn forget_pid(&self, id: WorkerId) {
        if let Some(pid) = id.value {
            self.pids.write().await.remove(&pid);
        }
    }

    pub async fn recv(&self) -> Result<Worker> {
        // The guard must be held while waiting for a worker
        // so that the waiter is accounted until `recv` returns
        // (or the future is dropped).
        let _waiter = WaiterGuard::acquire(&self.waiters, self.max_waiters())?;
        let start = Instant::now();
        let worker = self.q.recv().await?;
        self.wait_time.record(start.elapsed());
        Ok(worker)
    }

    // Return the restore lock
    pub fn restore(&self) -> &RwLock<Restore> {
        &self.restore
    }

    // Update the worker by acquiring the restore read lock
    async fn update(&self, worker: &mut Worker) -> Result<()> {
        self.restore.read().await.restore(worker).await
    }

    // Terminate a worker
    async fn terminate(&self, mut w: Worker) -> Result<()> {
        self.num_workers.fetch_sub(1, Ordering::Relaxed);
        w.terminate().await
    }

    // Terminate a worker in increase the failure count
    async fn terminate_failure(&self, w: Worker) -> Result<()> {
        self.failures.fetch_add(1, Ordering::Relaxed);
        self.terminate(w).await
    }

    pub fn nominal(&self) -> usize {
        self.nominal.load(Ordering::Relaxed)
    }

    // Reserve the removal of a surplus worker
    //
    // Atomically decrement the number of live workers if it is
    // above the nominal number; returns false otherwise.
    // This guarantees that concurrent removals never bring the
    // number of workers below the nominal number.
    fn reserve_surplus(&self) -> bool {
        let nominal = self.nominal();
        self.num_workers
            .try_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n > nominal).then(|| n - 1)
            })
            .is_ok()
    }

    // Remove up to n surplus idle workers from queue
    // Returns the number of workers removed
    async fn remove_surplus(&self, n: usize) -> usize {
        let mut count = 0;
        while count < n && self.reserve_surplus() {
            match self.q.drain(1).pop() {
                Some(mut w) => {
                    let _ = w.terminate().await;
                    count += 1;
                }
                None => {
                    // No idle worker: release the reservation,
                    // busy workers are retired when recycled.
                    self.num_workers.fetch_add(1, Ordering::AcqRel);
                    break;
                }
            }
        }
        count
    }

    // Remove n workers from queue
    async fn remove(&self, n: usize) -> usize {
        let mut removed = self.q.drain(n);
        let count = removed.len();
        self.num_workers.fetch_sub(count, Ordering::Relaxed);
        for mut w in removed.drain(..) {
            let _ = w.terminate().await;
        }
        count
    }

    //
    // Recycler
    //
    // `done_hint` is a hint to set for preventing draining any remaining
    // leftover data in case of incomplete response.
    //
    pub(crate) async fn recycle_owned(
        self: Arc<Self>,
        mut worker: Worker,
        done_hint: bool,
    ) -> Result<()> {
        let pid = worker.id();

        if self.is_closed() {
            let _ = self.terminate(worker).await;
            return Ok(());
        }

        log::debug!("Recycling worker [{pid}]");

        self.forget_pid(pid).await;

        // Check if worker must be replaced
        if worker.generation < self.generation() {
            return self.terminate(worker).await;
        }

        // Check if worker has reached its maximum life cycles
        if self.life_cycles_exhausted(&worker) {
            log::info!("Worker [{pid}] reached EOL");
            return self.terminate(worker).await;
        }

        // Retire the worker if there is more live workers than
        // the nominal number (i.e the pool has been scaled down
        // while all workers were busy).
        if self.reserve_surplus() {
            log::info!("Retiring surplus worker [{pid}]");
            return worker.terminate().await;
        }

        // Try graceful cancel
        let rv = match worker.cancel_timeout(done_hint).await {
            Ok(_) => {
                // Updateresources
                let rv = self.update(&mut worker).await;
                if rv.is_ok() {
                    // Send back worker to queue
                    self.q.send(worker).await;
                    return Ok(());
                }
                rv
            }
            Err(err) => Err(err),
        }
        .inspect_err(|err| {
            log::error!("Worker [{pid}] recycling failure with error:: {err}");
        });

        self.terminate_failure(worker).await?;
        rv
    }

    #[inline(always)]
    pub fn drain<B, F: FnMut(Worker) -> B>(&self, f: F) -> Vec<B> {
        self.q.drain_map(f)
    }
    #[inline(always)]
    fn close(&self) {
        self.q.close();
    }
    #[inline(always)]
    pub fn is_closed(&self) -> bool {
        self.q.is_closed()
    }
}

// RAII guard counting a waiter
struct WaiterGuard<'a>(&'a AtomicUsize);

impl<'a> WaiterGuard<'a> {
    fn acquire(waiters: &'a AtomicUsize, max_waiters: usize) -> Result<Self> {
        if waiters.fetch_add(1, Ordering::AcqRel) >= max_waiters {
            waiters.fetch_sub(1, Ordering::AcqRel);
            Err(Error::MaxRequestsExceeded)
        } else {
            Ok(Self(waiters))
        }
    }
}

impl Drop for WaiterGuard<'_> {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

//
// Pool
//

/// A pool of Worker
///
/// Manage multiple worker with the same configuration.
///
/// All methods take `&self`, so the pool can be shared with
/// `Arc<Pool>` without an external lock: operations that change the
/// number of workers are serialized internally, and starting new
/// workers does not block other accesses to the pool
/// (stats, configuration...).
pub struct Pool {
    queue: Arc<WorkerQueue>,
    // Held only for short synchronous sections:
    // never held across an await point.
    builder: parking_lot::RwLock<Builder>,
    error: AtomicBool,
    // Serialize operations that change the number of workers
    scaling: Mutex<()>,
}

impl Pool {
    /// Create a new pool instance from a Worker builder
    pub fn new(mut builder: Builder) -> Self {
        let opts = builder.options_mut();
        let num_processes = clamp_processes(opts, opts.num_processes());
        let max_waiting_requests = opts.max_waiting_requests();
        let max_life_cycles = opts.max_life_cycles;
        Self {
            queue: Arc::new(WorkerQueue {
                q: Queue::with_capacity(num_processes),
                num_workers: AtomicUsize::new(0),
                nominal: AtomicUsize::new(num_processes),
                max_waiters: AtomicUsize::new(max_waiting_requests),
                max_life_cycles: AtomicUsize::new(max_life_cycles),
                waiters: AtomicUsize::new(0),
                wait_time: WaitTimeRecorder::default(),
                restore: RwLock::new(Restore::with_projects(opts.restore_projects.drain(..))),
                generation: AtomicUsize::new(1),
                failures: AtomicUsize::new(0),
                pids: RwLock::new(HashSet::new()),
            }),
            builder: parking_lot::RwLock::new(builder),
            error: AtomicBool::new(false),
            scaling: Mutex::new(()),
        }
    }

    pub fn set_error(&self) {
        self.error.store(true, Ordering::Relaxed)
    }

    pub fn has_error(&self) -> bool {
        self.error.load(Ordering::Relaxed)
    }

    /// Returns a copy of the worker options
    pub fn options(&self) -> WorkerOptions {
        self.builder.read().options().clone()
    }

    /// Patch configuration
    ///
    /// If the patch sets `num_processes`, the nominal number of workers
    /// is reset to that value; otherwise the current nominal number
    /// is kept, bounded by the (possibly updated) `min_processes`
    /// and `max_processes`.
    pub async fn patch_config(&self, patch: &serde_json::Value) -> Result<()> {
        let _scaling = self.scaling.lock().await;
        {
            let mut builder = self.builder.write();
            builder.patch(patch)?;
            let opts = builder.options();
            self.queue.set_max_waiters(opts.max_waiting_requests());
            self.queue.set_max_life_cycles(opts.max_life_cycles);
            let num_processes = if patch
                .get("worker")
                .and_then(|w| w.get("num_processes"))
                .is_some()
            {
                opts.num_processes()
            } else {
                self.num_processes()
            };
            self.queue
                .nominal
                .store(clamp_processes(opts, num_processes), Ordering::Relaxed);
        }
        self.scale().await
    }

    /// Returns the nominal number of workers
    pub fn num_processes(&self) -> usize {
        self.queue.nominal()
    }

    /// Returns the lower bound of the number of workers
    pub fn min_processes(&self) -> usize {
        self.builder.read().options().min_processes()
    }

    /// Returns the upper bound of the number of workers
    pub fn max_processes(&self) -> usize {
        self.builder.read().options().max_processes()
    }

    /// Returns the maximum number of requests waiting for a worker
    pub fn max_waiting_requests(&self) -> usize {
        self.queue.max_waiters()
    }

    /// Set the nominal number of workers and scale the pool accordingly
    ///
    /// The value is bounded by `min_processes..=max_processes`.
    /// Returns the effective nominal number of workers.
    ///
    /// When scaling down, idle workers are terminated immediately;
    /// if not enough workers are idle, busy workers are retired
    /// when they are recycled.
    pub async fn set_num_processes(&self, n: usize) -> Result<usize> {
        let _scaling = self.scaling.lock().await;
        let n = clamp_processes(self.builder.read().options(), n);
        let current = self.queue.nominal.swap(n, Ordering::Relaxed);
        if n != current {
            log::info!("Setting number of workers: {current} -> {n}");
        }
        self.scale().await.map(|_| n)
    }

    pub(crate) fn clone_queue(&self) -> Arc<WorkerQueue> {
        self.queue.clone()
    }

    /// Returns the number of failures
    pub fn failures(&self) -> usize {
        self.queue.failures.load(Ordering::Relaxed)
    }

    /// Returns the number of waiters for available
    /// worker
    #[inline(always)]
    pub fn num_waiters(&self) -> usize {
        self.queue.num_waiters()
    }

    /// Returns the cumulative time spent by requests
    /// waiting for a worker
    pub fn wait_stats(&self) -> WaitStats {
        self.queue.wait_time.snapshot()
    }

    /// Returns the number of live  workers
    pub fn num_workers(&self) -> usize {
        self.queue.num_workers.load(Ordering::Relaxed)
    }

    /// Returns the ratio of failures against
    /// the maximum number of workers
    ///
    /// The maximum number of workers is used as reference so that
    /// the ratio does not depend on the actual nominal number of workers.
    pub fn failure_pressure(&self) -> f64 {
        self.failures() as f64 / self.max_processes() as f64
    }

    /// Return memoized pids
    pub async fn inspect_pids(&self) -> Vec<i32> {
        self.queue
            .pids
            .read()
            .await
            .iter()
            .map(|id| *id as i32)
            .collect::<Vec<_>>()
    }

    pub(crate) fn stats_raw(&self) -> (usize, usize) {
        let idle = self.queue.q.len();
        let busy = self.num_workers().saturating_sub(idle);
        (busy, idle)
    }

    /// Clean dead workers by removing them
    /// from queue
    ///
    /// Normally, this should not happend since no dead workers
    /// should reach the queue, but it may happends that an idle
    /// worker may die for whatever reason, usually indicating that
    /// something goes wrong
    fn cleanup_dead_workers(&self) {
        let dead_workers = self.queue.q.retain(|w| w.is_alive());
        if dead_workers > 0 {
            log::warn!("Removed {dead_workers} dead workers from queue !");
            // Remove dead workers from the count of live workers
            self.queue
                .num_workers
                .fetch_sub(dead_workers, Ordering::Relaxed);
        }
    }

    /// Maintain the pool at nominal number of live workers
    pub async fn maintain_pool(&self) -> Result<()> {
        let _scaling = self.scaling.lock().await;
        self.scale().await
    }

    // Bring the number of live workers to the nominal number.
    // Must be called with the `scaling` lock held.
    async fn scale(&self) -> Result<()> {
        self.cleanup_dead_workers();
        let nominal = self.num_processes();
        let failures = self.failures();
        let current = self.num_workers();

        match nominal.cmp(&current) {
            cmp::Ordering::Greater => self.grow(nominal - current).await,
            cmp::Ordering::Less => self.shrink(current - nominal).await,
            cmp::Ordering::Equal => Ok(()),
        }
        // Reset failures count
        .inspect(|_| {
            self.queue.failures.fetch_sub(failures, Ordering::Relaxed);
        })
    }

    /// Add workers to the pool
    async fn grow(&self, n: usize) -> Result<()> {
        if self.queue.is_closed() {
            return Err(Error::QueueIsClosed);
        }

        let ts = Instant::now();

        // Release the builder lock before spawning
        let launcher = self.builder.read().launcher();

        log::debug!("Launching {n} workers");
        let futures: Vec<_> = (0..n).map(|_| launcher.clone().spawn()).collect();

        // Start the workers asynchronously
        let mut workers = try_join_all(futures).await?;

        let generation = self.queue.generation();

        // Resync
        try_join_all(workers.iter_mut().map(|w| {
            w.generation = generation;
            self.queue.update(w)
        }))
        .await?;

        // Update the queue
        self.queue.q.send_all(workers.drain(..));
        self.queue.num_workers.fetch_add(n, Ordering::Relaxed);
        log::info!("Started {} workers in {} ms", n, ts.elapsed().as_millis());
        Ok(())
    }

    /// Remove workers from the pool
    async fn shrink(&self, n: usize) -> Result<()> {
        if self.queue.is_closed() {
            return Err(Error::QueueIsClosed);
        }
        log::debug!("Pool: Shrinking by {n} workers");
        let removed = self.queue.remove_surplus(n).await;
        if removed < n {
            log::debug!(
                "Pool: {} busy workers will be retired when recycled",
                n - removed
            );
        }
        Ok(())
    }

    /// Close the pool and shutdown all workers with a grace period
    pub async fn close(&self, grace_period: Duration) {
        // Close the queue: no workers will be available anymore
        log::info!("Closing worker queue");
        self.queue.close();

        let throttle = Duration::from_secs(1);
        // Wait for all active workers
        let _ = tokio::time::timeout(grace_period, async {
            log::info!("Waiting for active workers....");
            loop {
                let (active, _) = self.stats_raw();
                if active > 0 {
                    log::debug!("Active workers: {active}");
                    tokio::time::sleep(throttle).await;
                } else {
                    log::info!("No active workers");
                    break;
                }
            }
        })
        .await;
        // Wait for any scaling in progress, so that workers
        // being started are queued before draining the queue.
        let _scaling = self.scaling.lock().await;
        // Drain all idle workers
        log::info!("Shutting down...");
        let num_workers = self.num_workers();
        let remain = num_workers.saturating_sub(self.queue.remove(num_workers).await);
        log::debug!("Pool terminated (rem:  {remain})");
    }
}

// Bound the number of workers to `min_processes..=max_processes`
fn clamp_processes(opts: &WorkerOptions, n: usize) -> usize {
    // Do not use `usize::clamp` which panics if min > max
    n.max(opts.min_processes()).min(opts.max_processes())
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::receiver::Receiver;
    use crate::tests::setup;

    fn builder(num_processes: usize) -> Builder {
        let mut builder = Builder::new(crate::rootdir!("process.py"));
        let _ = builder
            .name("test")
            .process_start_timeout(5)
            .num_processes(num_processes)
            .unwrap();
        builder
    }

    #[tokio::test]
    async fn test_pool() {
        setup();

        let mut num_processes = 3;
        let mut builder = builder(num_processes);
        builder.processes_bounds(1, num_processes).unwrap();
        let pool = Pool::new(builder);

        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_workers(), num_processes);
        assert_eq!(pool.stats_raw(), (0, num_processes));

        // Shrink the number of workers
        num_processes -= 1;
        pool.set_num_processes(num_processes).await.unwrap();
        assert_eq!(pool.num_workers(), num_processes);
        assert_eq!(pool.stats_raw(), (0, num_processes));

        // Get a Receiver
        let queue = Receiver::new(&pool);

        let mut worker = queue.get().await.unwrap();
        assert_eq!(pool.stats_raw(), (1, num_processes - 1));

        assert_eq!(worker.ping("hello").await.unwrap(), "hello");
        worker.done();

        let _ = worker.recycle().unwrap().await.unwrap();
        assert_eq!(pool.stats_raw(), (0, num_processes));
    }

    #[tokio::test]
    async fn test_max_life_cycles() {
        setup();

        let mut builder = builder(1);
        builder.max_life_cycles(2);
        let pool = Pool::new(builder);

        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_workers(), 1);

        let queue = Receiver::new(&pool);

        // Below the limit: worker is sent back to the queue
        let mut worker = queue.get().await.unwrap();
        assert_eq!(worker.incr_life_cycles(), 1);
        worker.done();
        worker.recycle().unwrap().await.unwrap().unwrap();
        assert_eq!(pool.num_workers(), 1);
        assert_eq!(pool.stats_raw(), (0, 1));

        // Limit reached: worker is terminated on recycling
        let mut worker = queue.get().await.unwrap();
        assert_eq!(worker.life_cycles(), 1);
        assert_eq!(worker.incr_life_cycles(), 2);
        worker.done();
        worker.recycle().unwrap().await.unwrap().unwrap();
        assert_eq!(pool.num_workers(), 0);
        assert_eq!(pool.failures(), 0);

        // Pool is restored with a fresh worker
        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_workers(), 1);
        let worker = queue.get().await.unwrap();
        assert_eq!(worker.life_cycles(), 0);
    }

    #[tokio::test]
    async fn test_max_waiters() {
        setup();

        let mut builder = builder(1);
        builder.options_mut().max_waiting_requests = 2.try_into().unwrap();
        let pool = Pool::new(builder);
        pool.maintain_pool().await.unwrap();

        let queue = Receiver::new(&pool);

        // Take the only worker: no waiters
        let worker = queue.get().await.unwrap();
        assert_eq!(pool.num_waiters(), 0);
        let prev = pool.wait_stats();
        assert_eq!(prev.count, 1);

        // Two requests wait for a worker
        let w1 = tokio::spawn({
            let queue = queue.clone();
            async move { queue.get().await.map(|_| ()) }
        });
        let w2 = tokio::spawn({
            let queue = queue.clone();
            async move { queue.get().await.map(|_| ()) }
        });
        while pool.num_waiters() < 2 {
            tokio::task::yield_now().await;
        }
        assert_eq!(pool.num_waiters(), 2);

        // Max waiters reached
        assert!(matches!(
            queue.get().await,
            Err(Error::MaxRequestsExceeded)
        ));
        assert_eq!(pool.num_waiters(), 2);

        // Cancelled waiters are released
        w2.abort();
        let _ = w2.await;
        assert_eq!(pool.num_waiters(), 1);

        // Released worker is handed over to the waiter
        let delay = Duration::from_millis(100);
        tokio::time::sleep(delay).await;
        drop(worker);
        w1.await.unwrap().unwrap();
        assert_eq!(pool.num_waiters(), 0);

        // Only the request that obtained a worker is accounted
        let stats = pool.wait_stats();
        assert_eq!(stats.count, 2);
        assert!(stats.mean_since(&prev).unwrap() >= delay);
        assert!(stats.max >= delay);
    }

    #[tokio::test]
    async fn test_set_num_processes() {
        setup();

        let mut builder = builder(2);
        builder.processes_bounds(1, 3).unwrap();
        let pool = Pool::new(builder);

        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_processes(), 2);
        assert_eq!(pool.num_workers(), 2);

        // Grow
        assert_eq!(pool.set_num_processes(3).await.unwrap(), 3);
        assert_eq!(pool.num_workers(), 3);

        // Bounded by max_processes
        assert_eq!(pool.set_num_processes(5).await.unwrap(), 3);
        assert_eq!(pool.num_workers(), 3);

        // Shrink, bounded by min_processes
        assert_eq!(pool.set_num_processes(0).await.unwrap(), 1);
        assert_eq!(pool.num_workers(), 1);
        assert_eq!(pool.stats_raw(), (0, 1));

        // Failure pressure is relative to max_processes
        pool.queue.failures.store(3, Ordering::Relaxed);
        assert_eq!(pool.failure_pressure(), 1.0);
        pool.queue.failures.store(0, Ordering::Relaxed);

        // Patching without `num_processes` keeps the nominal value
        pool.patch_config(&serde_json::json!({
            "worker": { "max_processes": 4 }
        }))
        .await
        .unwrap();
        assert_eq!(pool.num_processes(), 1);
        assert_eq!(pool.max_processes(), 4);

        // ...but bounds it to the new limits
        pool.patch_config(&serde_json::json!({
            "worker": { "min_processes": 2 }
        }))
        .await
        .unwrap();
        assert_eq!(pool.num_processes(), 2);
        assert_eq!(pool.num_workers(), 2);

        // Patching `num_processes` resets the nominal value
        pool.patch_config(&serde_json::json!({
            "worker": { "num_processes": 3 }
        }))
        .await
        .unwrap();
        assert_eq!(pool.num_processes(), 3);
        assert_eq!(pool.num_workers(), 3);

        // Inconsistent configuration is rejected
        assert!(
            pool.patch_config(&serde_json::json!({
                "worker": { "num_processes": 5 }
            }))
            .await
            .is_err()
        );
        assert_eq!(pool.num_processes(), 3);
    }

    #[tokio::test]
    async fn test_concurrent_scaling() {
        setup();

        let mut builder = builder(1);
        builder.processes_bounds(1, 4).unwrap();
        let pool = Arc::new(Pool::new(builder));
        pool.maintain_pool().await.unwrap();

        // Concurrent scaling operations must not overshoot
        let scaling = tokio::spawn({
            let pool = pool.clone();
            async move { pool.set_num_processes(3).await }
        });
        let (r1, r2) = tokio::join!(pool.maintain_pool(), pool.maintain_pool());
        r1.unwrap();
        r2.unwrap();
        assert_eq!(scaling.await.unwrap().unwrap(), 3);
        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_workers(), 3);
        assert_eq!(pool.stats_raw(), (0, 3));

        // Pool remains accessible while workers are starting
        let scaling = tokio::spawn({
            let pool = pool.clone();
            async move { pool.set_num_processes(4).await }
        });
        tokio::task::yield_now().await;
        let _ = crate::stats::Stats::new(pool.as_ref());
        assert_eq!(pool.max_processes(), 4);
        scaling.await.unwrap().unwrap();
        assert_eq!(pool.num_workers(), 4);

        // Close waits for workers and terminates them
        pool.close(Duration::from_secs(1)).await;
        assert_eq!(pool.num_workers(), 0);
    }

    #[tokio::test]
    async fn test_retire_busy_workers() {
        setup();

        let mut builder = builder(3);
        builder.processes_bounds(1, 3).unwrap();
        let pool = Pool::new(builder);
        pool.maintain_pool().await.unwrap();

        let queue = Receiver::new(&pool);

        // All workers busy
        let mut w1 = queue.get().await.unwrap();
        let mut w2 = queue.get().await.unwrap();
        let mut w3 = queue.get().await.unwrap();
        assert_eq!(pool.stats_raw(), (3, 0));

        // Scale down: no idle worker can be removed
        assert_eq!(pool.set_num_processes(1).await.unwrap(), 1);
        assert_eq!(pool.num_workers(), 3);

        // Busy workers are retired when recycled
        w1.done();
        w1.recycle().unwrap().await.unwrap().unwrap();
        assert_eq!(pool.num_workers(), 2);
        assert_eq!(pool.stats_raw(), (2, 0));

        // Concurrent recycling never goes below the nominal number
        w2.done();
        w3.done();
        let (r2, r3) = tokio::join!(w2.recycle().unwrap(), w3.recycle().unwrap());
        r2.unwrap().unwrap();
        r3.unwrap().unwrap();
        assert_eq!(pool.num_workers(), 1);
        assert_eq!(pool.stats_raw(), (0, 1));
        // Retiring is not a failure
        assert_eq!(pool.failures(), 0);
    }

    #[tokio::test]
    async fn test_shrink_keeps_nominal() {
        setup();

        let mut builder = builder(3);
        builder.processes_bounds(1, 3).unwrap();
        let pool = Pool::new(builder);
        pool.maintain_pool().await.unwrap();

        // Shrinking more than the surplus never goes below nominal
        pool.shrink(3).await.unwrap();
        assert_eq!(pool.num_workers(), 3);

        pool.queue.nominal.store(2, Ordering::Relaxed);
        pool.shrink(3).await.unwrap();
        assert_eq!(pool.num_workers(), 2);
        assert_eq!(pool.stats_raw(), (0, 2));
    }

    use crate::restore;

    #[tokio::test]
    async fn test_restore() {
        setup();

        let pool = Pool::new(builder(1));
        {
            let mut restore = pool.queue.restore().write().await;
            restore.update_cache(restore::State::Pull("project_1".into()));
        }
        pool.maintain_pool().await.unwrap();

        let queue = Receiver::new(&pool);
        {
            let mut worker = queue.get().await.unwrap();
            let resp = worker.checkout_project("project_1", false).await.unwrap();
            assert_eq!(resp.status, 0); // UNCHANGED
        }

        // Update project's
        queue
            .update_cache(restore::State::Pull("project_2".into()))
            .await;

        {
            let mut worker = queue.get().await.unwrap();
            let resp = worker.checkout_project("project_2", false).await.unwrap();
            assert_eq!(resp.status, 0); // UNCHANGED
        }
    }

    #[tokio::test]
    async fn test_patch_config() {
        setup();

        let num_processes = 3;
        let pool = Pool::new(builder(num_processes));

        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.num_workers(), num_processes);
        assert_eq!(pool.stats_raw(), (0, num_processes));

        pool.patch_config(&serde_json::json!({
            "logging": {
                "level": "debug"
            },
        }))
        .await
        .unwrap();

        assert_eq!(pool.num_workers(), num_processes);
        assert_eq!(pool.stats_raw(), (0, num_processes));
    }
}
