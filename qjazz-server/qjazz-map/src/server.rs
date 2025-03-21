use actix_web::{
    App, HttpResponse, HttpServer, Result, body,
    body::EitherBody,
    dev::{ServiceRequest, ServiceResponse},
    middleware, web,
};

use futures::future::try_join_all;
use tokio_util::sync::CancellationToken;

use crate::channel::{self, Channel};
use crate::config::Settings;
use crate::handlers::utils::request;
use crate::resolver::Channels;
use crate::services::{api_scope, catalog, landing_page, ows_resource};

// Log request as '[REQ:<request id>] ...'
const LOGGER_FORMAT: &str =
    r#"[REQ:%{x-request-id}i] %a "%r" %s %b "%{Referer}i" "%{User-Agent}i" %D"#;

pub async fn serve(settings: Settings) -> Result<(), Box<dyn std::error::Error>> {
    let token = CancellationToken::new();

    // Handle channel's connection
    let backends = Backends::connect(settings.backends).await?;

    let server_conf = settings.server;

    let tls_config = server_conf.tls_config()?;
    let bind_address = server_conf.bind_address();
    let proxy_headers = request::ProxyHeaders {
        allow: server_conf.check_forwarded_headers(),
    };

    let shutdown_timeout = server_conf.shutdown_timeout();
    let num_workers = server_conf.num_workers();

    let cors = server_conf.cors;

    backends.watch(token);

    let server = HttpServer::new(move || {
        App::new()
            .wrap(cors.configure())
            .wrap(middleware::NormalizePath::trim())
            .wrap(middleware::from_fn(server_mw))
            .app_data(web::ThinData(proxy_headers))
            .configure(backends.clone().configure())
            .wrap(middleware::Logger::new(LOGGER_FORMAT))
    })
    .shutdown_timeout(shutdown_timeout);

    if let Some(tls_config) = tls_config {
        server.bind_rustls_0_23(&bind_address, tls_config)
    } else {
        server.bind(&bind_address)
    }?
    .workers(num_workers)
    .run()
    .await?;

    Ok(())
}

// Single channel config
fn single_channel_scope(channel: web::Data<Channel>) -> impl FnOnce(&mut web::ServiceConfig) {
    |cfg| {
        let cfg = cfg
            .service(web::scope("/").configure(ows_resource))
            .configure(catalog);
        channel
            .api_endpoints()
            .iter()
            .fold(cfg, |cfg, api| cfg.configure(api_scope(api.clone())))
            .app_data(channel);
    }
}

// Create channel configuration
fn multi_channel_scope(channel: web::Data<Channel>) -> impl FnOnce(&mut web::ServiceConfig) {
    let scope = web::scope(channel.route())
        .wrap(middleware::from_fn(verify_channel_mw))
        .configure(catalog)
        .configure(ows_resource);

    // Add api endpoints
    let scope = channel
        .api_endpoints()
        .iter()
        .fold(scope, |s, api| s.configure(api_scope(api.clone())))
        .app_data(channel);

    |cfg| {
        cfg.service(scope);
    }
}

#[derive(Clone)]
enum Backends {
    Single(web::Data<Channel>),
    Multi(Vec<web::Data<Channel>>),
}

// Convert channel configurations to Channel
impl Backends {
    pub async fn connect(cfgs: Channels) -> Result<Self, channel::Error> {
        if cfgs.is_single_root_channel() {
            // We have only one channel
            let (name, cfg) = cfgs.into_iter().next().unwrap();
            let channel = Channel::builder(name, cfg).connect().await?;
            Ok(Self::Single(web::Data::new(channel)))
        } else {
            // Sort channels by inverse route order (longest first)
            let mut channels = try_join_all(
                cfgs.into_iter()
                    .rev()
                    .map(|(name, cfg)| Channel::builder(name, cfg).connect()),
            )
            .await?;
            Ok(Self::Multi(
                channels.drain(..).map(web::Data::new).collect(),
            ))
        }
    }

    fn watch(&self, token: CancellationToken) {
        match self {
            Self::Single(channel) => channel.watch(token),
            Self::Multi(channels) => channels
                .iter()
                .for_each(|channel| channel.watch(token.clone())),
        }
    }

    fn configure(self) -> impl FnOnce(&mut web::ServiceConfig) {
        move |cfg| {
            match self {
                Backends::Single(channel) => cfg.configure(single_channel_scope(channel)),
                Backends::Multi(channels) => channels
                    .iter()
                    .fold(cfg, |cfg, channel| {
                        cfg.configure(multi_channel_scope(channel.clone()))
                    })
                    .configure(landing_page(channels)),
            };
        }
    }
}

//
// Middlewares
//
async fn server_mw(
    req: ServiceRequest,
    next: middleware::Next<impl body::MessageBody>,
) -> Result<ServiceResponse<impl body::MessageBody>> {
    // See https://docs.rs/actix-web/latest/actix_web/trait.HttpMessage.html#tymethod.extensions_mut
    // for adding data

    let mut resp = next.call(req).await?;

    // Normalize headers to camel case
    // for buggy clients
    resp.response_mut().head_mut().set_camel_case_headers(true);
    Ok(resp)
}

// Early check that channel is serving
async fn verify_channel_mw(
    req: ServiceRequest,
    next: middleware::Next<impl body::MessageBody>,
) -> Result<ServiceResponse<EitherBody<impl body::MessageBody>>> {
    // Check if channel is serving
    if let Some(channel) = req.app_data::<web::Data<Channel>>() {
        if !channel.serving() {
            let name = channel.name().to_string();
            return Ok(req.into_response(
                HttpResponse::ServiceUnavailable()
                    .content_type("text/plain")
                    .body(format!(
                        "Service '{}' not available, please retry later",
                        name
                    ))
                    .map_into_right_body(),
            ));
        }
    }
    Ok(next.call(req).await?.map_into_left_body())
}
