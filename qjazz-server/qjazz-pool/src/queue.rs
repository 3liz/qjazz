//!
//! Async queue implementations
//!
//!
use crate::errors::{Error, Result};
use parking_lot::Mutex;
use std::collections::VecDeque;
use std::sync::atomic::{AtomicUsize, Ordering};
use tokio::sync::Semaphore;

pub struct Queue<T> {
    queue: Mutex<VecDeque<T>>,
    avails: Semaphore,
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
            avails: Semaphore::new(0),
            pending: AtomicUsize::new(0),
        }
    }

    /// Wait for object on the queue, returns `Err(Error::QueueIsClosed)` if the Queue is closed.
    pub async fn recv(&self) -> Result<T> {
        self.pending.fetch_add(1, Ordering::Relaxed);
        self.avails
            .acquire()
            .await
            .map_err(|_| Error::QueueIsClosed)?
            .forget();
        let item = self
            .queue
            .lock()
            .pop_front()
            .expect("FATAL: workers queue is empty while permits are availables !!!");
        self.pending.fetch_sub(1, Ordering::Relaxed);
        Ok(item)
    }

    /// Send an item to the queue
    pub async fn send(&self, item: T) {
        self.queue.lock().push_back(item);
        self.avails.add_permits(1)
    }

    /// Retain only the elements specified by the predicate
    ///
    /// Returns the mumber of elements removed
    pub fn retain<F>(&self, f: F) -> usize
    where
        F: FnMut(&mut T) -> bool,
    {
        let mut q = self.queue.lock();
        let initial = q.len();
        q.retain_mut(f);
        self.avails.forget_permits(initial - q.len())
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
        self.avails.add_permits(count);
    }

    /// Remove at most n elements
    /// Returns the elements removed
    pub fn drain(&self, n: usize) -> Vec<T> {
        let mut q = self.queue.lock();
        let count = usize::min(n, q.len());
        let v = q.drain(0..count).collect();
        _ = self.avails.forget_permits(count);
        v
    }

    /// Drain all elements
    pub fn drain_map<B, F>(&self, f: F) -> Vec<B>
    where
        F: FnMut(T) -> B,
    {
        let mut q = self.queue.lock();
        let v: Vec<_> = q.drain(..).map(f).collect();
        _ = self.avails.forget_permits(v.len());
        v
    }

    /// Close the queue and notify all waiters
    #[inline(always)]
    pub fn close(&self) {
        self.avails.close();
    }

    /// Returns `true` if the queue is closed
    #[inline(always)]
    pub fn is_closed(&self) -> bool {
        self.avails.is_closed()
    }

    /// Returns the number of elements in the queue
    #[inline(always)]
    pub fn len(&self) -> usize {
        self.avails.available_permits()
    }

    /// Returns the number of waiters
    pub fn num_waiters(&self) -> usize {
        self.pending.load(Ordering::Relaxed)
    }
}
