//!
//! Crate errors
//!
#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("IO error")]
    IoError(#[from] std::io::Error),
    #[error("Pickle error")]
    PickleError(#[from] serde_pickle::Error),
    #[error("Response error {0}: {1}")]
    ResponseError(i64, serde_json::Value),
    #[error("System error")]
    Errno(#[from] nix::errno::Errno),
    #[error("Error: {0}")]
    Worker(String),
    #[error("Worker process is dead")]
    WorkerProcessDead,
    #[error("Worker process not started")]
    WorkerProcessNotStarted,
    #[error("Worker process failed prematuraly")]
    WorkerProcessFailure,
    #[error("Worker stalled")]
    WorkerStalled,
    #[error("Worker response error: {0}")]
    WorkerResponse(i64, serde_json::Value),
    #[error("Worker child no ready")]
    WorkerProcessNotReady,
    #[error("Response data expected !")]
    ResponseExpected,
    #[error("Unexpected empty chunk !")]
    EmptyChunk,
    #[error("Unexpected no data response")]
    NoDataResponse,
    #[error("Unexpected response")]
    UnexpectedResponse,
    #[error("IO Buffer overflow")]
    IoBufferOverflow,
    #[error("Rendez-vous was disconnected")]
    RendezVousDisconnected,
    #[error("Failed to send message length")]
    MessageHeaderFailure,
    #[error("The queue is closed")]
    QueueIsClosed,
    #[error("Max number of waiters/requets exceeded")]
    MaxRequestsExceeded,
    #[error("Task failed")]
    TaskFailed(String),
    #[error("Timeout error")]
    Timeout,
    #[error("Missing or invalid config value {0}")]
    InvalidConfigValue(String),
    #[error("Invalid HTTP method {0}")]
    InvalidHttpMethod(String),
}

pub type Result<T, E = Error> = std::result::Result<T, E>;

impl From<Error> for String {
    fn from(err: Error) -> String {
        format!("{}", err)
    }
}
