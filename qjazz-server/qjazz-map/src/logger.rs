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

        let qjazz_log_defined = std::env::var_os("QJAZZ_LOG").is_some();

        // Force qjazz modules to log with the specified log level
        // but allow global module specification from the "QJAZZ_LOG" env
        // variable so that we activate logging for external crates.
        env_logger::Builder::from_env(
            env_logger::Env::default()
                .filter_or("QJAZZ_LOG", "error")
                .write_style("QJAZZ_LOG_STYLE"),
        )
        .filter(Some("qjazz_map"), self.level)
        .filter(Some("actix_server"), self.level)
        .filter(Some("actix_web::middleware::logger"), self.level)
        .format(move |buf, record| {
            if qjazz_log_defined {
                writeln!(
                    buf,
                    "{}\t[{}]\t{:5}\t{}",
                    buf.timestamp_millis(),
                    record.module_path().unwrap_or_default(),
                    record.level(),
                    record.args()
                )
            } else {
                writeln!(
                    buf,
                    "{}\t{:5}\t{}",
                    buf.timestamp_millis(),
                    record.level(),
                    record.args()
                )
            }
        })
        .init();

        eprintln!("Log level set to {}", log::max_level());
    }
}
