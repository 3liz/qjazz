//
// Restorer
// Resync workers with a list of projects or config state
//
use crate::errors::Result;
use crate::worker::Worker;
use std::collections::BTreeMap;

// Project states
#[derive(Debug, Copy, Clone)]
pub enum State {
    Pull,
    Drop,
}

// Store project states
#[derive(Default)]
pub struct Restore {
    // Update count
    update: u64,
    states: BTreeMap<String, State>,
}

impl Restore {
    pub fn new() -> Self {
        Self::default()
    }
    pub async fn restore(&self, worker: &mut Worker) -> Result<()> {
        if worker.last_update < self.update {
            log::debug!("Updating worker {}", worker.id());
            for (uri, state) in &self.states {
                match state {
                    State::Pull => worker.checkout_project(uri, true).await,
                    State::Drop => worker.drop_project(uri).await,
                }?;
            }
            worker.last_update = self.update;
        }
        Ok(())
    }
    // End the update by incrementing the update counter
    pub fn end_update(&mut self) {
        self.update += 1;
    }
    // Update project state
    pub fn update_state<S: Into<String>>(&mut self, uri: S, state: State) {
        self.states.insert(uri.into(), state);
    }
    // Update multiple project states
    pub fn update_states<I, S>(&mut self, iter: I)
    where
        I: IntoIterator<Item = (S, State)>,
        S: Into<String>,
    {
        self.states
            .extend(iter.into_iter().map(|(k, s)| (k.into(), s)));
    }
}
