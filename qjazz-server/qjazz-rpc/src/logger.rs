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
                    "{}\t[{}]\t{:5}\t{}",
                    buf.timestamp_millis(),
                    record.module_path().unwrap_or_default(),
                    record.level(),
                    record.args()
                )
            });
        } else {
            builder.format(|buf, record| {
                writeln!(
                    buf,
                    "{}\t[main]\t{:5}\t{}",
                    buf.timestamp_millis(),
                    record.level(),
                    record.args()
                )
            });
        }

        builder.init();
    }
}
