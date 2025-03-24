//!
//! Implement monitoring for OWS requests
//!


#[cfg(feature = "monitor")]
mod mon {
    use actix_web::{
        body,
        dev::{ServiceRequest, ServiceResponse},
        http::StatusCode,
        middleware, web,
    };
    use qjazz_mon::{Config, Error, Monitor};
    use serde::Serialize;
    use std::collections::HashMap;
    use std::sync::Arc;
    use tokio::time::Instant;
    use tokio_util::sync::CancellationToken;

    use crate::handlers::ows::Ows;

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

    #[derive(Debug)]
    pub struct Params {
        args: Ows,
        instant: Instant,
    }

    impl Params {
        fn from(args: Ows) -> Self {
            Self {
                args,
                instant: Instant::now(),
            }
        }
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

    static NOTSET: &str = "<notset>";

    impl Sender {
        pub fn is_configured(&self) -> bool {
            self.0.is_some()
        }

        pub fn send(&self, params: Params, status: StatusCode) -> Result<(), Error> {
            log::debug!("[Monitor] sending message {:?}", params);
            if let Some(tx) = &self.0 {
                let msg = Msg {
                    service: params.args.service,
                    request: params.args.request.unwrap_or(NOTSET.to_string()),
                    map: params.args.map.unwrap_or(NOTSET.to_string()),
                    response_time: params.instant.elapsed().as_millis() as u64,
                    response_status: status.as_u16(),
                    tags: tx.tags.clone(),
                };
                tx.tx
                    .try_send(msg)
                    .map_err(|e| Error::SendError(format!("{e}")))
            } else {
                Err(Error::SendError("Monitor is not configured".to_string()))
            }
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

            let task = monitor.run().await?;

            actix_web::rt::spawn(async move {
                if let Err(e) = task.await {
                    log::error!("FATAL: Unrecoverable monitor failure: {e}");
                    token.cancel();
                }
            });
            Ok((Sender(Some(tx)), Some(tok)))
        } else {
            Ok((Sender(None), None))
        }
    }

    //
    //  Monitor middleware for ows requests
    //
    //  NOTE: we expect thah the request has `service`, `request` and `map` as
    //  query params (either for POST and GET)
    //
    pub async fn middleware(
        mut req: ServiceRequest,
        next: middleware::Next<impl body::MessageBody>,
    ) -> actix_web::Result<ServiceResponse<impl body::MessageBody>> {
        let mon = req
            .app_data::<web::ThinData<Sender>>()
            .expect("Sender must be declared as thin application data!")
            .clone();

        let params = if mon.is_configured() {
            req.extract::<web::Query<Ows>>()
                .await
                .ok()
                .map(|args| Params::from(args.into_inner()))
        } else {
            None
        };

        let resp = next.call(req).await?;

        if let Some(params) = params {
            let _ = mon.send(params, resp.status()).inspect_err(|e| {
                log::error!("Monitor: failed to send message: {e}");
            });
        }
        Ok(resp)
    }
}

#[cfg(not(feature = "monitor"))]
mod mon {
    #[derive(Clone)]
    pub struct Sender {}
}

pub use mon::*;
