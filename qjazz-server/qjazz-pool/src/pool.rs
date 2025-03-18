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
use crate::worker::{Worker, WorkerId};
use futures::future::try_join_all;
use std::collections::HashSet;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;

pub(crate) struct WorkerQueue {
    q: Queue<Worker>,
    dead_workers: AtomicUsize,
    max_requests: AtomicUsize,
    generation: AtomicUsize,
    failures: AtomicUsize,
    restore: RwLock<Restore>,
    // Keep a list of busy worker's pid
    // used for checking processe's resources
    // of busy workers.
    pids: RwLock<HashSet<u32>>,
}

impl WorkerQueue {
    pub fn max_requests(&self) -> usize {
        self.max_requests.load(Ordering::Relaxed)
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
        if self.q.num_waiters() > self.max_requests() {
            return Err(Error::MaxRequestsExceeded);
        }
        self.q.recv().await
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
        self.dead_workers.fetch_add(1, Ordering::Relaxed);
        w.terminate().await
    }

    // Terminate a worker in increase the failure count
    async fn terminate_failure(&self, w: Worker) -> Result<()> {
        self.failures.fetch_add(1, Ordering::Relaxed);
        self.terminate(w).await
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
        log::debug!("Recycling worker [{}]", pid);

        self.forget_pid(pid).await;

        // Check if worker must be replaced
        if worker.generation < self.generation() {
            self.terminate(worker).await
        } else {
            // Try graceful cancel
            let mut rv = worker.cancel_timeout(done_hint).await;
            if rv.is_ok() {
                // Update resources
                rv = self.update(&mut worker).await;
                if rv.is_ok() {
                    self.q.send(worker).await;
                } else {
                    self.terminate_failure(worker).await?;
                }
            } else {
                // Cancel failed, terminate the worker
                let id = worker.id();
                self.terminate_failure(worker).await?;
                log::error!("Killed stalled process {}", id);
            }
            rv
        }
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

//
// Pool
//

/// A pool of Worker
///
/// Manage multiple worker with the same configuration.
pub struct Pool {
    queue: Arc<WorkerQueue>,
    builder: Builder,
    num_processes: usize,
    error: bool,
}

impl Pool {
    /// Create a new pool instance from a Worker builder
    pub fn new(mut builder: Builder) -> Self {
        let opts = builder.options_mut();
        Self {
            queue: Arc::new(WorkerQueue {
                q: Queue::with_capacity(opts.num_processes()),
                dead_workers: AtomicUsize::new(0),
                max_requests: AtomicUsize::new(opts.max_waiting_requests()),
                restore: RwLock::new(Restore::with_projects(opts.restore_projects.drain(..))),
                generation: AtomicUsize::new(1),
                failures: AtomicUsize::new(0),
                pids: RwLock::new(HashSet::new()),
            }),
            builder,
            num_processes: 0,
            error: false,
        }
    }

    pub fn set_error(&mut self) {
        self.error = true
    }

    pub fn has_error(&mut self) -> bool {
        self.error
    }

    pub(crate) fn options(&self) -> &WorkerOptions {
        self.builder.options()
    }

    /// Patch configuration
    pub async fn patch_config(&mut self, patch: &serde_json::Value) -> Result<()> {
        self.builder.patch(patch)?;
        self.queue.max_requests.store(
            self.builder.options().max_waiting_requests(),
            Ordering::Relaxed,
        );
        self.maintain_pool().await
    }

    pub(crate) fn clone_queue(&self) -> Arc<WorkerQueue> {
        self.queue.clone()
    }

    /// Returns the number of dead workers
    pub fn dead_workers(&self) -> usize {
        self.queue.dead_workers.load(Ordering::Relaxed)
    }

    /// Returns the number of failures
    pub fn failures(&self) -> usize {
        self.queue.failures.load(Ordering::Relaxed)
    }

    /// Returns the number of waiters for available
    /// worker
    pub fn num_waiters(&self) -> usize {
        self.queue.q.num_waiters()
    }

    /// Returns the number of worker created so far
    pub fn num_workers(&self) -> usize {
        self.num_processes
    }

    /// Returns the ratio of failures against
    /// the number of created workers
    pub fn failure_pressure(&self) -> f64 {
        self.failures() as f64 / self.num_processes as f64
    }

    /// Inspect memoized pids
    pub async fn inspect_pids<F>(&self, mut f: F)
    where
        F: FnMut(Vec<i32>),
    {
        // Ensure acquiring the locks during the shortest time
        // as possible.
        let processes = {
            self.queue
                .pids
                .write()
                .await
                .iter()
                .map(|id| *id as i32)
                .collect::<Vec<_>>()
        };

        f(processes);
    }

    pub(crate) fn stats_raw(&self) -> (usize, usize, usize) {
        let dead = self.dead_workers();
        let idle = self.queue.q.len();
        let busy = self.num_processes - idle - dead;
        (busy, idle, dead)
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
            log::warn!("Removed {} dead workers from queue !", dead_workers);
            self.queue
                .dead_workers
                .fetch_add(dead_workers, Ordering::Relaxed);
        }
    }

    /// Maintain the pool at nominal number of live workers
    pub async fn maintain_pool(&mut self) -> Result<()> {
        self.cleanup_dead_workers();
        let nominal = self.builder.options().num_processes();
        let dead_workers = self.dead_workers();
        let failures = self.failures();
        let current = self.num_processes - dead_workers;

        #[allow(clippy::comparison_chain)]
        let rv = if nominal > current {
            self.grow(nominal - current).await.inspect(|_| {
                self.num_processes = nominal;
                self.queue.failures.fetch_sub(failures, Ordering::Relaxed);
                self.queue
                    .dead_workers
                    .fetch_sub(dead_workers, Ordering::Relaxed);
            })
        } else if nominal < current {
            self.shrink(current - nominal).await.inspect(|_| {
                self.queue.failures.fetch_sub(failures, Ordering::Relaxed);
                self.queue
                    .dead_workers
                    .fetch_sub(dead_workers, Ordering::Relaxed);
            })
        } else {
            Ok(())
        };
        rv
    }

    /// Add workers to the pool
    async fn grow(&mut self, n: usize) -> Result<()> {
        if self.queue.is_closed() {
            return Err(Error::QueueIsClosed);
        }

        let ts = Instant::now();

        log::debug!("Launching {} workers", n);
        let futures: Vec<_> = (0..n).map(|_| self.builder.clone().start_owned()).collect();

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
        self.num_processes += n;
        log::info!("Started {} workers in {} ms", n, ts.elapsed().as_millis());
        Ok(())
    }

    /// Remove workers from the pool
    async fn shrink(&mut self, n: usize) -> Result<()> {
        if self.queue.is_closed() {
            return Err(Error::QueueIsClosed);
        }
        log::debug!("Pool: Shrinking by {} workers", n);
        let mut removed = self.queue.q.drain(n);
        self.num_processes -= removed.len();
        for mut w in removed.drain(..) {
            let _ = w.terminate().await;
        }
        Ok(())
    }

    /// Close the pool and shutdown all workers with a grace period
    pub async fn close(&mut self, grace_period: Duration) {
        // Close the queue: no workers will be available anymore
        log::info!("Closing worker queue");
        self.queue.close();

        let throttle = Duration::from_secs(1);
        // Wait for all active workers
        let _ = tokio::time::timeout(grace_period, async {
            log::info!("Waiting for active workers....");
            loop {
                let (active, _, _) = self.stats_raw();
                if active > 0 {
                    log::debug!("Active workers: {}", active);
                    tokio::time::sleep(throttle).await;
                } else {
                    log::debug!("No active workers");
                    break;
                }
            }
        })
        .await;
        // Drain all idle workers
        log::info!("Shutting down...");
        let mut removed = self.queue.q.drain(self.num_processes);
        self.num_processes -= removed.len();
        for mut w in removed.drain(..) {
            let _ = w.terminate().await;
        }
        log::debug!("Pool terminated (rem:  {})", self.num_processes);
    }
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
        let mut builder = Builder::new(&[crate::rootdir!("process.py")]);
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
        let mut pool = Pool::new(builder(num_processes));

        pool.maintain_pool().await.unwrap();
        assert_eq!(pool.stats_raw(), (0, num_processes, 0));

        // Shrink the number of workers
        pool.shrink(1).await.unwrap();
        num_processes -= 1;
        assert_eq!(pool.stats_raw(), (0, num_processes, 0));

        // Get a Receiver
        let queue = Receiver::new(&pool);

        let mut worker = queue.get().await.unwrap();
        assert_eq!(pool.stats_raw(), (1, num_processes - 1, 0));

        assert_eq!(worker.ping("hello").await.unwrap(), "hello");
        worker.done();

        let _ = worker.recycle().unwrap().await.unwrap();
        assert_eq!(pool.stats_raw(), (0, num_processes, 0));
    }

    use crate::restore;

    #[tokio::test]
    async fn test_restore() {
        setup();

        let mut pool = Pool::new(builder(1));
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
}
