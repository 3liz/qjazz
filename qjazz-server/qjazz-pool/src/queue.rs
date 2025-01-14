//!
//! Async queue implementations
//!
//!
use crate::errors::{Error, Result};
use parking_lot::Mutex;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use tokio::sync::Notify;

pub struct Queue<T> {
    queue: Mutex<VecDeque<T>>,
    notify: Notify,
    closed: AtomicBool,
    count: AtomicUsize,
    pending: AtomicUsize,
}

impl<T> Default for Queue<T> {
    fn default() -> Self {
        Self::new()
    }
}

impl<T> Queue<T> {
    pub fn new() -> Self {
        Self::from_queue(VecDeque::new())
    }

    pub fn with_capacity(capacity: usize) -> Self {
        Self::from_queue(VecDeque::with_capacity(capacity))
    }

    fn from_queue(queue: VecDeque<T>) -> Self {
        Self {
            queue: Mutex::new(queue),
            notify: Notify::new(),
            closed: AtomicBool::new(false),
            count: AtomicUsize::new(0),
            pending: AtomicUsize::new(0),
        }
    }

    /// Wait for object on the queue, returns `None` if the Queue is closed.
    /// Once the queue is closed `recv` will always return `None`
    pub async fn recv(&self) -> Result<T> {
        loop {
            if self.is_closed() {
                return Err(Error::QueueIsClosed);
            }
            // Drain the queue
            if let Some(item) = self.queue.lock().pop_front() {
                self.count.fetch_sub(1, Ordering::Relaxed);
                return Ok(item);
            }
            // Wait for value to be available
            self.pending.fetch_add(1, Ordering::Relaxed);
            self.notify.notified().await;
            self.pending.fetch_sub(1, Ordering::Relaxed);
        }
    }

    /// Send an item to the queue
    pub async fn send(&self, item: T) {
        self.queue.lock().push_back(item);
        self.count.fetch_add(1, Ordering::Relaxed);
        self.notify.notify_one();
    }

    /// Send a list object to the queue
    pub fn send_all<I>(&self, iter: I)
    where
        I: IntoIterator<Item = T>,
    {
        let mut q = self.queue.lock();
        let count = iter
            .into_iter()
            .map(|item| {
                q.push_back(item);
                1
            })
            .count();
        // Update count
        self.count.store(q.len(), Ordering::Relaxed);
        (0..count).for_each(|_| self.notify.notify_one());
    }

    /// Remove at most n elements
    /// Returns the number of element removed
    pub fn drain(&self, n: usize) -> Vec<T> {
        let mut q = self.queue.lock();
        let count = usize::min(n, q.len());
        let v = q.drain(0..count).collect();
        self.count.store(q.len(), Ordering::Relaxed);
        v
    }

    /// Drain all elements
    pub fn drain_map<B, F>(&self, f: F) -> Vec<B>
    where
        F: FnMut(T) -> B,
    {
        let mut q = self.queue.lock();
        let v = q.drain(..).map(f).collect();
        self.count.store(0, Ordering::Relaxed);
        v
    }

    /// Close the queue and notify all waiters
    pub fn close(&self) {
        self.closed.store(true, Ordering::Relaxed);
        self.notify.notify_waiters();
    }

    /// Returns `true` if the queue is closed
    pub fn is_closed(&self) -> bool {
        self.closed.load(Ordering::Relaxed)
    }

    /*
    /// Returns 'true' if the queue is empty
    pub fn is_empty(&self) -> bool {
        self.count.load(Ordering::Relaxed) == 0
    }
    */

    /// Returns the number of elements in the queue
    pub fn len(&self) -> usize {
        self.count.load(Ordering::Relaxed)
    }

    /// Returns the number of waiters
    pub fn num_waiters(&self) -> usize {
        self.pending.load(Ordering::Relaxed)
    }
}
