use serde::{Deserialize, Deserializer, Serialize, de};
use std::fmt;
use std::str::FromStr;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Logging {
    #[serde(deserialize_with = "deserialize_level_filter")]
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
        let mut builder = env_logger::Builder::from_env(
            env_logger::Env::default()
                .filter_or("QJAZZ_LOG", "error")
                .write_style("QJAZZ_LOG_STYLE"),
        );

        #[cfg(feature = "monitor")]
        builder.filter(Some("qjazz_mon"), self.level);

        builder
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

// XXX Workaround: hit by https://github.com/rust-lang/log/issues/532
fn deserialize_level_filter<'de, D>(des: D) -> Result<log::LevelFilter, D::Error>
where
    D: Deserializer<'de>,
{
    struct Visitor;

    impl de::Visitor<'_> for Visitor {
        type Value = log::LevelFilter;

        fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
            formatter.write_str("Expecting string in 'error', 'warning', 'debug', 'info'")
        }

        fn visit_str<E>(self, value: &str) -> Result<Self::Value, E>
        where
            E: de::Error,
        {
            log::LevelFilter::from_str(value).map_err(|e| {
                de::Error::invalid_value(de::Unexpected::Other(&format!("{e}")), &self)
            })
        }
    }

    des.deserialize_str(Visitor)
}
