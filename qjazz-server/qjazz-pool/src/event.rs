//!
//! Create the a Event synchronization primitive that remember its last value.
//! This is the equivalent of Python `asyncio.Event`. 
//!
use tokio::sync::watch;

#[derive(Default, Clone)]
pub struct Event(watch::Sender<bool>);

impl Event {
    pub fn new() -> Self {
        Self(watch::Sender::new(false))
    }

    /// Set the event.
    ///
    /// All tasks waiting for event to be set will be immediately awakened.
    pub fn set(&self) {
        // send_replace, not send: does not fail when there are no waiters
        self.0.send_replace(true);
    }

    /// Clear (unset) the event.
    ///
    /// Subsequent tasks awaiting on wait() will now block until the set() 
    /// method is called again.
    pub fn clear(&self) {
        self.0.send_replace(false);
    }

    /// Return true if the event is set.
    pub fn is_set(&self) -> bool {
        *self.0.borrow()
    }

    /// Wait until the event is set.
    ///
    /// If the event is set, return True immediately. Otherwise block until 
    /// another task calls set().
    pub async fn wait(&self) {
        // `wait_for` evaluates the predicate against the *current* value first,
        // then on every change, holding the lock — so no set() can slip through
        // between the check and the registration.
        let _ = self.0.subscribe().wait_for(|v| *v).await;
    }
}
