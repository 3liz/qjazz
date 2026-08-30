//!
//! Restorer
//! Resync workers with a list of projects or config state
//!
use crate::errors::Result;
use crate::worker::Worker;
use std::collections::{BTreeSet, VecDeque};

const MAX_STATES: usize = 256;

/// Project states
#[derive(Debug, Clone)]
pub enum State {
    Pull(String),
    Remove(String),
    Clear,
    Update,
}

/// Store project states
pub struct Restore {
    // Update count
    update: u64,
    // TODO: bound pulled list
    pulls: BTreeSet<String>,
    config: (u64, serde_json::Value),
    states: VecDeque<(u64, State)>,
    initial_update: u64,
}

impl Default for Restore {
    fn default() -> Self {
        Self {
            pulls: BTreeSet::new(),
            update: 1, // 1 is the first state after initial update
            states: VecDeque::new(),
            initial_update: 0, // Initial update
            config: (0, serde_json::Value::Null),
        }
    }
}

impl Restore {
    pub fn with_projects<I: IntoIterator<Item = String>>(iter: I) -> Self {
        Self {
            pulls: iter.into_iter().collect(),
            ..Default::default()
        }
    }

    async fn update_worker_config(&self, worker: &mut Worker) -> Result<()> {
        if self.config.0 > worker.last_update {
            log::debug!("Updating configuration for worker {}", worker.id());
            worker.put_config(&self.config.1).await?;
        }
        Ok(())
    }

    async fn update_worker_cache(&self, worker: &mut Worker) -> Result<()> {
        let last_update = worker.last_update;
        if last_update <= self.initial_update {
            worker.clear_cache().await?;
            // Update with all pulled projects so far
            for uri in &self.pulls {
                worker.checkout_project(uri, true).await?;
            }
        } else if last_update < self.update {
            // We need to catch up with updated states
            // Update cache
            worker.update_cache().await?;
            for rev in self.states.iter().skip_while(|rev| rev.0 <= last_update) {
                // Replay states forward.
                // prevent Remove -> Pull/Pull -> Remove sequence with the same uri by
                // checking their existence in the pulled list.
                match &rev.1 {
                    State::Pull(uri) => {
                        if self.pulls.contains(uri) {
                            worker.checkout_project(uri, true).await?;
                        }
                    }
                    State::Remove(uri) => {
                        if !self.pulls.contains(uri) {
                            worker.drop_project(uri).await?;
                        }
                    }
                    // Clear is always the first state
                    State::Clear => worker.clear_cache().await?,
                    State::Update => (),
                };
            }
        }
        Ok(())
    }

    pub async fn restore(&self, worker: &mut Worker) -> Result<()> {
        self.update_worker_config(worker).await?;
        self.update_worker_cache(worker).await?;
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
                // Clear all previous states
                self.pulls.clear();
                self.states.clear();
            }
            State::Update => {
                // Only increment
                self.update += 1;
                return;
            }
        }
        self.update += 1;
        self.states.push_back((self.update, state));

        // Cap states
        if self.states.len() > MAX_STATES {
            let (update, _) = self.states.pop_front().unwrap();
            self.initial_update = update;
        }
    }
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::builder::Builder;
    use crate::tests::setup;
    use crate::worker::ListCacheFilter;
    use serde_json::json;

    //
    // Helpers
    //

    // Return the recorded states as a readable (update, label) list
    fn state_log(restore: &Restore) -> Vec<(u64, String)> {
        restore
            .states
            .iter()
            .map(|(update, state)| {
                let label = match state {
                    State::Pull(uri) => format!("pull:{uri}"),
                    State::Remove(uri) => format!("remove:{uri}"),
                    State::Clear => "clear".into(),
                    State::Update => "update".into(),
                };
                (*update, label)
            })
            .collect()
    }

    fn pulls(restore: &Restore) -> Vec<&str> {
        restore.pulls.iter().map(String::as_str).collect()
    }

    async fn build_worker() -> Worker {
        Builder::new(crate::rootdir!("process.py"))
            .name("test")
            .process_start_timeout(5)
            .start()
            .await
            .unwrap()
    }

    // Return the sorted list of uris held in the worker's cache
    async fn cache_content(worker: &mut Worker) -> Vec<String> {
        let mut stream = worker.list_cache(ListCacheFilter::default()).await.unwrap();
        let mut uris = Vec::<String>::new();
        while let Some(info) = stream.next().await.unwrap() {
            uris.push(info.uri.clone());
        }
        uris.sort();
        uris
    }

    //
    // States bookkeeping
    //

    #[test]
    fn test_default_state() {
        let restore = Restore::default();
        assert_eq!(restore.update, 1);
        assert_eq!(restore.initial_update, 0);
        assert!(restore.pulls.is_empty());
        assert!(restore.states.is_empty());
        assert_eq!(restore.config, (0, serde_json::Value::Null));
    }

    #[test]
    fn test_with_projects() {
        let restore = Restore::with_projects(["proj_b".to_string(), "proj_a".to_string()]);
        // Projects are stored as an ordered set
        assert_eq!(pulls(&restore), ["proj_a", "proj_b"]);
        // freshly spawned worker (see `test_restore_initial_projects`).
        assert_eq!(restore.update, 1);
        assert!(restore.states.is_empty());
    }

    #[test]
    fn test_update_config() {
        let mut restore = Restore::default();

        restore.update_config(json!({"foo": 1}));
        assert_eq!(restore.update, 2);
        assert_eq!(restore.config, (2, json!({"foo": 1})));

        restore.update_config(json!({"foo": 2}));
        assert_eq!(restore.update, 3);
        assert_eq!(restore.config, (3, json!({"foo": 2})));

        // Configuration updates do not record any cache state
        assert!(restore.states.is_empty());
    }

    #[test]
    fn test_pull_state() {
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        assert_eq!(restore.update, 2);
        assert_eq!(pulls(&restore), ["proj_1"]);
        assert_eq!(state_log(&restore), [(2, "pull:proj_1".to_string())]);
    }

    #[test]
    fn test_pull_is_idempotent() {
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        // Pulling the same project again is a no-op: neither the counter
        // nor the states are updated.
        restore.update_cache(State::Pull("proj_1".into()));

        assert_eq!(restore.update, 2);
        assert_eq!(pulls(&restore), ["proj_1"]);
        assert_eq!(state_log(&restore), [(2, "pull:proj_1".to_string())]);
    }

    #[test]
    fn test_remove_state() {
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Remove("proj_1".into()));

        assert_eq!(restore.update, 3);
        assert!(restore.pulls.is_empty());
        assert_eq!(
            state_log(&restore),
            [
                (2, "pull:proj_1".to_string()),
                (3, "remove:proj_1".to_string()),
            ]
        );
    }

    #[test]
    fn test_remove_unknown_is_noop() {
        let mut restore = Restore::default();

        restore.update_cache(State::Remove("proj_1".into()));

        assert_eq!(restore.update, 1);
        assert!(restore.states.is_empty());
    }

    #[test]
    fn test_clear_state() {
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Pull("proj_2".into()));
        restore.update_cache(State::Clear);

        // Clear drops all pulled projects and previous states,
        // and is always the first recorded state.
        assert!(restore.pulls.is_empty());
        assert_eq!(restore.update, 4);
        assert_eq!(state_log(&restore), [(4, "clear".to_string())]);

        // Following states are recorded after the clear
        restore.update_cache(State::Pull("proj_3".into()));
        assert_eq!(
            state_log(&restore),
            [(4, "clear".to_string()), (5, "pull:proj_3".to_string())]
        );
    }

    #[test]
    fn test_update_state_only_increments() {
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Update);

        assert_eq!(restore.update, 3);
        // No 'update' state is recorded
        assert_eq!(state_log(&restore), [(2, "pull:proj_1".to_string())]);
    }

    #[test]
    fn test_states_are_capped() {
        let mut restore = Restore::default();

        for i in 0..MAX_STATES {
            restore.update_cache(State::Pull(format!("proj_{i}")));
        }
        assert_eq!(restore.states.len(), MAX_STATES);
        assert_eq!(restore.initial_update, 0);

        // Overflow: the oldest states are dropped and `initial_update` is
        // moved forward accordingly.
        restore.update_cache(State::Pull("proj_overflow_1".into()));
        assert_eq!(restore.states.len(), MAX_STATES);
        assert_eq!(restore.initial_update, 2);
        assert_eq!(restore.states.front().unwrap().0, 3);

        restore.update_cache(State::Pull("proj_overflow_2".into()));
        assert_eq!(restore.states.len(), MAX_STATES);
        assert_eq!(restore.initial_update, 3);

        // Pulled projects are never dropped
        assert_eq!(restore.pulls.len(), MAX_STATES + 2);
    }

    //
    // Worker restoration
    //

    #[tokio::test]
    async fn test_restore_nothing_to_do() {
        setup();

        let mut worker = build_worker().await;
        let restore = Restore::default();

        restore.restore(&mut worker).await.unwrap();

        assert_eq!(worker.last_update, 1);
        assert!(cache_content(&mut worker).await.is_empty());
    }

    #[tokio::test]
    async fn test_restore_initial_projects() {
        setup();

        let mut worker = build_worker().await;
        let restore = Restore::with_projects(["proj_1".to_string()]);

        restore.restore(&mut worker).await.unwrap();

        // A freshly spawned worker will load initials projects
        assert_eq!(worker.last_update, 1);
        assert_eq!(cache_content(&mut worker).await, ["proj_1"]);
    }

    #[tokio::test]
    async fn test_restore_replays_pulls() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Pull("proj_2".into()));

        restore.restore(&mut worker).await.unwrap();

        assert_eq!(cache_content(&mut worker).await, ["proj_1", "proj_2"]);
        // The worker is now in sync
        assert_eq!(worker.last_update, restore.update);

        // Restoring again does not change anything
        restore.restore(&mut worker).await.unwrap();
        assert_eq!(cache_content(&mut worker).await, ["proj_1", "proj_2"]);
    }

    #[tokio::test]
    async fn test_restore_skips_pull_removed_afterward() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Pull("proj_2".into()));
        restore.update_cache(State::Remove("proj_1".into()));

        restore.restore(&mut worker).await.unwrap();

        // 'proj_1' is never pulled since it has been removed afterward
        assert_eq!(cache_content(&mut worker).await, ["proj_2"]);
    }

    #[tokio::test]
    async fn test_restore_drops_project() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.update_cache(State::Pull("proj_2".into()));
        restore.restore(&mut worker).await.unwrap();
        assert_eq!(cache_content(&mut worker).await, ["proj_1", "proj_2"]);

        // Catch up with the states recorded since the last restoration
        restore.update_cache(State::Remove("proj_1".into()));
        restore.update_cache(State::Pull("proj_3".into()));
        restore.restore(&mut worker).await.unwrap();

        assert_eq!(cache_content(&mut worker).await, ["proj_2", "proj_3"]);
        assert_eq!(worker.last_update, restore.update);
    }

    #[tokio::test]
    async fn test_restore_replays_clear() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.restore(&mut worker).await.unwrap();
        assert_eq!(cache_content(&mut worker).await, ["proj_1"]);

        restore.update_cache(State::Clear);
        restore.update_cache(State::Pull("proj_2".into()));
        restore.restore(&mut worker).await.unwrap();

        assert_eq!(cache_content(&mut worker).await, ["proj_2"]);
    }

    #[tokio::test]
    async fn test_restore_full_resync_on_states_overflow() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.restore(&mut worker).await.unwrap();
        assert_eq!(worker.last_update, 2);

        // Overflow the states buffer: the worker is now lagging behind
        // `initial_update` and cannot catch up incrementally.
        restore.update_cache(State::Remove("proj_1".into()));
        for i in 0..MAX_STATES {
            restore.update_cache(State::Pull(format!("proj_ovf_{i}")));
        }
        assert!(worker.last_update <= restore.initial_update);

        restore.restore(&mut worker).await.unwrap();

        // The cache has been cleared and repopulated with all pulled projects
        let content = cache_content(&mut worker).await;
        assert_eq!(content.len(), MAX_STATES);
        assert!(!content.contains(&"proj_1".to_string()));
        assert!(content.contains(&"proj_ovf_0".to_string()));
        assert_eq!(worker.last_update, restore.update);
    }

    #[tokio::test]
    async fn test_restore_update_state() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_cache(State::Pull("proj_1".into()));
        restore.restore(&mut worker).await.unwrap();

        // An 'Update' state only invalidates the workers
        restore.update_cache(State::Update);
        assert!(worker.last_update < restore.update);

        restore.restore(&mut worker).await.unwrap();

        assert_eq!(cache_content(&mut worker).await, ["proj_1"]);
        assert_eq!(worker.last_update, restore.update);
    }

    #[tokio::test]
    async fn test_restore_config() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_config(json!({"foo": "bar"}));
        restore.restore(&mut worker).await.unwrap();

        assert_eq!(worker.get_config().await.unwrap(), json!({"foo": "bar"}));
        assert_eq!(worker.last_update, restore.update);
    }

    #[tokio::test]
    async fn test_restore_config_up_to_date() {
        setup();

        let mut worker = build_worker().await;
        let mut restore = Restore::default();

        restore.update_config(json!({"foo": "bar"}));
        // Pretend that the worker has already been synced
        worker.last_update = restore.update;

        restore.restore(&mut worker).await.unwrap();

        // The configuration has not been pushed again
        assert_eq!(worker.get_config().await.unwrap(), json!({}));
    }
}
