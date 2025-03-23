#[derive(thiserror::Error, Debug)]
pub enum Error {
    #[error("Encode error: {0}")]
    EncodeError(#[from] rmp_serde::encode::Error),
    #[error("IO error: {0}")]
    IoError(#[from] std::io::Error),
    #[error("Message required")]
    MessageRequired,
    #[error("Send error: {0}")]
    SendError(String),
}
