#[cfg(feature = "monitor")]
mod mon {
    use actix_web::http::StatusCode;
    use qjazz_mon::{Config, Error, Monitor};
    use serde::Serialize;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tokio::time::Instant;
    use tokio_util::sync::CancellationToken;

    // The real message to be sent
    #[derive(Serialize)]
    struct Msg {
        map: String,
        service: String,
        request: String,
        response_time: u64,
        response_status: u16,
        #[serde(flatten)]
        tags: Arc<HashMap<String, String>>,
    }

    // Public message
    #[derive(Debug)]
    pub struct Message {
        map: String,
        service: String,
        request: String,
        instant: Instant,
    }

    // Wrap sender into Option and set to None
    // when monitor is not configured
    #[derive(Clone)]
    struct Inner {
        tx: qjazz_mon::Sender<Msg>,
        tags: Arc<HashMap<String, String>>,
    }

    #[derive(Clone)]
    pub struct Sender(Option<Inner>);

    impl Sender {
        pub fn new_message(&self, map: &str, service: &str, request: &str) -> Option<Message> {
            if self.0.is_some() {
                Some(Message {
                    map: map.to_string(),
                    service: service.to_string(),
                    request: request.to_string(),
                    instant: Instant::now(),
                })
            } else {
                None
            }
        }

        pub fn send(&self, message: Option<Message>, status: StatusCode) -> Result<(), Error> {
            log::debug!("[Monitor] sending message {:?}", message);
            if let Some(tx) = &self.0 {
                let m = message.ok_or(Error::MessageRequired)?;
                let msg = Msg {
                    map: m.map,
                    service: m.service,
                    request: m.request,
                    response_time: m.instant.elapsed().as_millis() as u64,
                    response_status: status.as_u16(),
                    tags: tx.tags.clone(),
                };
                let _ = tx.tx.try_send(msg).inspect_err(|e| {
                    log::error!("Monitor: failed to send message: {e}");
                });
            }
            Ok(())
        }
    }

    /// Start the monitor and return a Sender and a CancellationToken that will
    /// be triggered on fatal monitor error.
    pub async fn consume(
        conf: Option<Config>,
    ) -> Result<(Sender, Option<CancellationToken>), Error> {
        if let Some(conf) = conf {
            let monitor = Monitor::new(&conf);
            let tx = Inner {
                tx: monitor.sender().clone(),
                tags: Arc::new(conf.tags),
            };

            let token = CancellationToken::new();
            let tok = token.clone();

            let fut = monitor.run().await?;

            actix_web::rt::spawn(async move {
                if let Err(e) = fut.await {
                    log::error!("FATAL: Unrecoverable monitor failure: {e}");
                    token.cancel();
                }
            });
            Ok((Sender(Some(tx)), Some(tok)))
        } else {
            Ok((Sender(None), None))
        }
    }
}

#[cfg(not(feature = "monitor"))]
mod mon {
    #[derive(Clone)]
    pub struct Sender {}
}

pub use mon::*;
