use config::ConfigError;
use std::path::Path;

pub trait Validator {
    fn validate(&self) -> Result<(), ConfigError>;

    fn validate_filepath(p: &Path) -> Result<(), ConfigError> {
        if !p.exists() {
            Err(ConfigError::Message(format!(
                "File {} deos not exists !",
                p.to_string_lossy(),
            )))
        } else {
            Ok(())
        }
    }
}
