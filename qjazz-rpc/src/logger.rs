use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Logging {
    level: log::LevelFilter,
}

impl Default for Logging {
    fn default() -> Self {
        Logging {
            level: log::LevelFilter::Info,
        }
    }
}

impl Logging {
    pub(crate) fn init(&self) {
        use std::io::Write;

        let mut builder = env_logger::Builder::new();

        builder.filter_level(self.level);

        if self.level >= log::LevelFilter::Trace {
            builder.format(|buf, record| {
                writeln!(
                    buf,
                    "{} {:5} [{}] {}",
                    buf.timestamp(),
                    record.level(),
                    record.module_path().unwrap_or_default(),
                    record.args()
                )
            });
        } else {
            builder.format(|buf, record| {
                writeln!(
                    buf,
                    "{} {:5} {}",
                    buf.timestamp(),
                    record.level(),
                    record.args()
                )
            });
        }

        builder.init();
    }
}
