//
// Restorer
// Resync workers with a list of projects or config state
//
use crate::errors::Result;
use crate::worker::Worker;
use std::collections::BTreeSet;

// Project states
#[derive(Debug, Clone)]
pub enum State {
    Pull(String),
    Remove(String),
    Clear,
    Update,
}

// Store project states
#[derive(Default)]
pub struct Restore {
    // Update count
    update: u64,
    pulls: BTreeSet<String>,
    config: (u64, serde_json::Value),
    states: Vec<(u64, State)>,
}

impl Restore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_projects<I: IntoIterator<Item = String>>(iter: I) -> Self {
        Self {
            pulls: iter.into_iter().collect(),
            ..Default::default()
        }
    }

    pub async fn restore(&self, worker: &mut Worker) -> Result<()> {
        let last_update = worker.last_update;
        if last_update == 0 {
            // Update with all pulled projects so far
            for uri in &self.pulls {
                worker.checkout_project(uri, true).await?;
            }
        } else if last_update < self.update {
            // Update config
            if self.config.0 > last_update {
                log::debug!("Updating configuration for worker {}", worker.id());
                worker.put_config(&self.config.1).await?;
            }
            // Update cache
            worker.update_cache().await?;
            for rev in self.states.iter().rev() {
                if rev.0 <= last_update {
                    break;
                }
                match &rev.1 {
                    State::Pull(uri) => {
                        let _ = worker.checkout_project(uri, true).await?;
                    }
                    State::Remove(uri) => {
                        let _ = worker.drop_project(uri).await?;
                    }
                    State::Clear => worker.clear_cache().await?,
                    State::Update => (),
                };
            }
        }
        worker.last_update = self.update;
        Ok(())
    }

    pub fn update_config(&mut self, config: serde_json::Value) {
        self.update += 1;
        self.config = (self.update, config);
    }

    // Update states
    pub fn update_cache(&mut self, state: State) {
        match &state {
            State::Pull(uri) => {
                if self.pulls.contains(uri) {
                    return;
                }
                self.pulls.insert(uri.clone());
            }
            State::Remove(uri) => {
                if !self.pulls.contains(uri) {
                    return;
                }
                self.pulls.remove(uri);
            }
            State::Clear => {
                self.pulls.clear();
                self.states.clear();
            }
            State::Update => {
                self.update += 1;
                return;
            }
        }
        self.update += 1;
        self.states.push((self.update, state));
    }
}
