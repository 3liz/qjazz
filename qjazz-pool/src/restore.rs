//
// Restorer
//
// Resync workers with a list of projects
//
use crate::errors::Result;
use crate::worker::Worker;

pub struct Restore {
    update: u64,
}

impl Restore {
    pub fn new() -> Self {
        Self { update: 0 }
    }
    pub async fn restore(&self, worker: &mut Worker) -> Result<()> {
        if worker.last_update < self.update {
            todo!();
            worker.last_update += 1;
        }
        Ok(())
    }
}
