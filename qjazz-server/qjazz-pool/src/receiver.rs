//!
//! A receiver for fetching worker from Pool
//!
//!
use crate::errors::Result;
use crate::pool::{Pool, WorkerQueue};
use crate::restore;
use crate::worker::Worker;
use std::ops::{Deref, DerefMut};
use std::sync::Arc;
use tokio::task::JoinHandle;

/// A Receiver for worker
#[derive(Clone)]
pub struct Receiver {
    queue: Arc<WorkerQueue>,
}

/// RAII implementation of a scoped Worker
pub struct ScopedWorker {
    queue: Arc<WorkerQueue>,
    item: Option<Worker>,
    done: bool,
}

impl ScopedWorker {
    /// Indicate that complete response has been read
    ///
    /// This is a hint to tell the recycler that there
    /// is no data left to read from the process.
    pub fn done(&mut self) {
        self.done = true;
    }

    pub async fn remember(&self) {
        // Remember the worker's pid
        // so that we can inspect the process
        self.queue.remember_pid(self.id()).await
    }

    pub(crate) fn recycle(&mut self) -> Option<JoinHandle<Result<()>>> {
        self.item
            .take()
            .map(|w| tokio::spawn(self.queue.clone().recycle_owned(w, self.done)))
    }
}

// When dropping a ScopedWorker
// then attemps to recycle the worker
impl Drop for ScopedWorker {
    fn drop(&mut self) {
        self.recycle();
    }
}

//
// Deref/DerefMut to Worker for ScopedWorker
//
impl Deref for ScopedWorker {
    type Target = Worker;

    fn deref(&self) -> &Self::Target {
        self.item.as_ref().unwrap()
    }
}

impl DerefMut for ScopedWorker {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.item.as_mut().unwrap()
    }
}

//
// Receiver implementation
//
impl Receiver {
    /// Build a new receiver for the given pool
    pub fn new(pool: &Pool) -> Self {
        Self {
            queue: pool.clone_queue(),
        }
    }

    /// Wait for a worker to be available.
    pub async fn get(&self) -> Result<ScopedWorker> {
        self.queue.recv().await.map(|w| ScopedWorker {
            queue: self.queue.clone(),
            item: Some(w),
            done: false,
        })
    }

    /// Returns true if the queue is closed
    pub fn is_closed(&self) -> bool {
        self.queue.is_closed()
    }

    /// Drain all elements and get a scoped worker
    /// for each.
    pub fn drain(&self) -> Vec<ScopedWorker> {
        self.queue.drain(|w| ScopedWorker {
            queue: self.queue.clone(),
            item: Some(w),
            done: false,
        })
    }

    pub fn reload(&self) {
        self.queue.next_generation();
        let _ = self.drain(); // Will be terminated on drop
    }

    pub async fn update_cache(&self, state: restore::State) {
        let mut restore = self.queue.restore().write().await;
        let _ = self.drain(); // Will update on drop
        restore.update_cache(state);
    }

    pub async fn update_config(&self, config: serde_json::Value) {
        let mut restore = self.queue.restore().write().await;
        let _ = self.drain(); // Will update on drop
        restore.update_config(config);
    }
}
