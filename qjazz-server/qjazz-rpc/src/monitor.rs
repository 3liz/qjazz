//!
//! Implement monitoring for OWS requests
//!

#[cfg(feature = "monitor")]
mod mon {
    use qjazz_mon::{Config, Error, Monitor};
    use qjazz_pool::messages::JsonValue;
    use tokio_util::sync::CancellationToken;

    type Inner = qjazz_mon::Sender<JsonValue>;

    // Wrap sender into Option and set to None
    // when monitor is not configured

    #[derive(Clone)]
    pub struct Sender(Option<Inner>);

    impl Sender {
        #[inline]
        pub fn is_configured(&self) -> bool {
            self.0.is_some()
        }

        pub fn send(&self, report: JsonValue) -> Result<(), Error> {
            if let Some(tx) = &self.0 {
                log::debug!("[Monitor] sending message {report:?}");
                tx.try_send(report)
                    .map_err(|e| Error::SendError(format!("{e}")))?;
            }
            Ok(())
        }
    }

    /// Start the monitor and return a Sender
    pub async fn consume(conf: Option<Config>, token: CancellationToken) -> Result<Sender, Error> {
        if let Some(conf) = conf {
            let monitor = Monitor::new(&conf);
            let inner = monitor.sender().clone();

            let task = monitor.run().await?;

            tokio::spawn(async move {
                if let Err(e) = task.await {
                    log::error!("FATAL: Unrecoverable monitor failure: {e}");
                    token.cancel();
                }
            });
            Ok(Sender(Some(inner)))
        } else {
            Ok(Sender(None))
        }
    }
}

#[cfg(not(feature = "monitor"))]
mod mon {
    #[derive(Clone)]
    pub struct Sender {}

    impl Sender {
        #[inline]
        pub fn is_configured(&self) -> bool {
            false
        }
    }
}

pub use mon::*;
