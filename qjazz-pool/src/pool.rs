//!
//! Worker pool
//!
//! Manage multiple workers
//!
use crate::builder::Builder;
use crate::errors::{Error, Result};
use crate::queue::Queue;
use crate::stats::Stats;
use crate::worker::Worker;
use futures::future::try_join_all;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub(crate) struct WorkerQueue {
    q: Queue<Worker>,
    dead_workers: AtomicUsize,
    max_requests: usize,
}

impl WorkerQueue {
    #[inline(always)]
    pub fn is_closed(&self) -> bool {
        self.q.is_closed()
    }
    #[inline(always)]
    pub async fn recv(&self) -> Result<Worker> {
        if self.q.num_waiters() > self.max_requests {
            return Err(Error::MaxRequestsExceeded);
        }
        self.q.recv().await
    }

    //
    // Recycler
    //
    // `done_hint` is a hint to set for preventing draining any remaining
    // leftover data in case of incomplete response.
    //
    pub(crate) async fn recycle(
        queue: Arc<Self>,
        mut worker: Worker,
        done_hint: bool,
    ) -> Result<()> {
        log::debug!("Recycling worker [{}]", worker.id());
        let rv = worker.cancel_timeout(done_hint).await;
        if rv.is_ok() {
            // Push back worker on queue
            queue.q.send(worker).await;
        } else {
            queue.dead_workers.fetch_add(1, Ordering::Relaxed);
        }
        rv
    }

    fn close(&self) {
        self.q.close();
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
}

impl Pool {
    /// Create a new pool instance from a Worker builder
    pub fn new(builder: Builder) -> Self {
        let opts = builder.options();
        Self {
            queue: Arc::new(WorkerQueue {
                q: Queue::with_capacity(opts.num_processes),
                dead_workers: AtomicUsize::new(0),
                max_requests: opts.max_waiting_requests,
            }),
            builder,
            num_processes: 0,
        }
    }

    pub(crate) fn clone_queue(&self) -> Arc<WorkerQueue> {
        self.queue.clone()
    }

    /// Returns the number of dead workers
    pub fn dead_workers(&self) -> usize {
        self.queue.dead_workers.load(Ordering::Relaxed)
    }

    /// Returns the number of waiters for available
    /// worker
    pub fn num_waiters(&self) -> usize {
        self.queue.q.num_waiters()
    }

    /// Return the number of worker created so far
    pub fn num_workers(&self) -> usize {
        self.num_processes
    }

    pub(crate) fn stats_raw(&self) -> (usize, usize, usize) {
        let dead = self.dead_workers();
        let idle = self.queue.q.len();
        let busy = self.num_processes - idle - dead;
        (busy, idle, dead)
    }

    /// Return statistics about workers state
    pub fn stats(&self) -> Stats {
        Stats::from_raw_stats(self.stats_raw(), Instant::now())
    }

    /// Maintain the pool at nominal number of live workers
    pub async fn maintain_pool(&mut self) -> Result<()> {
        let nominal = self.builder.options().num_processes;
        let current = self.num_processes - self.dead_workers();
        #[allow(clippy::comparison_chain)]
        let rv = if nominal > current {
            self.grow(nominal - current).await
        } else if nominal < current {
            self.shrink(current - nominal).await
        } else {
            Ok(())
        };
        // Clean up dead workers
        self.queue.dead_workers.store(0, Ordering::Relaxed);
        rv
    }

    /// Add workers to the pool
    async fn grow(&mut self, n: usize) -> Result<()> {
        if self.queue.is_closed() {
            return Err(Error::QueueIsClosed);
        }

        let ts = Instant::now();

        log::debug!("Pool: launching {} workers", n);
        let futures: Vec<_> = (0..n).map(|_| self.builder.clone().start_owned()).collect();

        // Start the workers asynchronously
        let mut workers = try_join_all(futures).await?;

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
            loop {
                let (active, _, _) = self.stats_raw();
                if active > 0 {
                    log::debug!("Active workers: {}", active);
                    tokio::time::sleep(throttle).await;
                } else {
                    log::info!("No active workers");
                    break;
                }
            }
        }).await;
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
        builder
            .name("test")
            .process_start_timeout(5)
            .num_processes(num_processes);
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
}
