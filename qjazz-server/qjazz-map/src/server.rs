use actix_web::{
    body,
    dev::{ServiceRequest, ServiceResponse},
    error, guard, middleware, web, App, HttpServer, Result,
};

use futures::future::try_join_all;
use tokio_util::sync::CancellationToken;

use crate::channel::{self, Channel};
use crate::config::Settings;
use crate::handlers::{api, ows, utils::request};
use crate::resolver::{ApiEndPoint, Channels};

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
        let app = App::new()
            .wrap(cors.configure())
            .wrap(middleware::Logger::new(LOGGER_FORMAT))
            .wrap(middleware::NormalizePath::trim())
            .wrap(middleware::from_fn(server_mw))
            .app_data(web::ThinData(proxy_headers));

        match backends.clone() {
            Backends::Single(channel) => app
                //.configure(dataset_collections)
                .configure(single_channel_scope(&channel))
                .app_data(web::Data::new(channel)),
            Backends::Multi(mut channels) => channels.drain(..).fold(app, |app, channel| {
                app.configure(multi_channel_scope(channel))
            }),
        }
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

//
// Services
//

/*

// Service config for layer collections
fn layer_collections(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::scope("/collections")
            .route("", ...)
            .service(
                web::scope("/{layer}")
                    .route("", ...)
                    .route("/map", ...)
                    .route("/items", ...),
            ),
    );
}

// Service config for  dataset collections
fn dataset_collections(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::scope("/collections")
            .route("", ...)
            .service(
                web::scope("/{dataset}")
                    .route("", ...)
                    .route("/map", ...)
                    .configure(layer_collections),
            ),
    );
}
*/

// Configuration for api endpoint
fn api_scope(api: web::Data<ApiEndPoint>) -> impl FnOnce(&mut web::ServiceConfig) {
    let path = format!("/{}", api.endpoint);

    let scope = web::scope(path.as_str())
        .app_data(api.clone())
        .route("{path:.*}", web::to(api::handler))
        .default_service(web::to(api::default_handler));

    move |cfg| {
        cfg.service(scope)
            .service(
                web::resource(format!("{}.json", path).as_str())
                    .app_data(api.clone())
                    .to(api::default_handler),
            )
            .service(
                web::resource(format!("{}.html", path).as_str())
                    .app_data(api.clone())
                    .to(api::default_handler),
            );
    }
}

// Configuration for handling OWS resources
fn ows_resource(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::resource("")
            .route(
                web::post()
                    .guard(guard::Header(
                        "content-type",
                        "application/x-www-form-urlencoded",
                    ))
                    .to(ows::form_handler),
            )
            .route(web::to(ows::query_handler)),
    );
}

// Single channel config
fn single_channel_scope(channel: &Channel) -> impl FnOnce(&mut web::ServiceConfig) {
    let scope = web::scope(channel.route())
        .wrap(middleware::from_fn(verify_channel_mw))
        .configure(ows_resource);

    // Add api endpoints
    let scope = channel
        .api_endpoints()
        .iter()
        .fold(scope, |s, api| s.configure(api_scope(api.clone())));

    |cfg| {
        cfg.service(scope);
    }
}

// Create channel configuration
fn multi_channel_scope(channel: web::Data<Channel>) -> impl FnOnce(&mut web::ServiceConfig) {
    let scope = web::scope(channel.route())
        .wrap(middleware::from_fn(verify_channel_mw))
        //.configure(dataset_collections)
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

    pub fn watch(&self, token: CancellationToken) {
        match self {
            Self::Single(channel) => channel.watch(token),
            Self::Multi(channels) => channels
                .iter()
                .for_each(|channel| channel.watch(token.clone())),
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

    // Normalize headers to camel case
    // for buggy clients

    let mut resp = next.call(req).await?;
    resp.response_mut().head_mut().set_camel_case_headers(true);
    Ok(resp)
}

// A channel middleware for early returns
// of unavailable channels
async fn verify_channel_mw(
    req: ServiceRequest,
    next: middleware::Next<impl body::MessageBody>,
) -> Result<ServiceResponse<body::EitherBody<body::BoxBody, impl body::MessageBody>>> {
    // Check channel availability
    if let Some(channel) = req.app_data::<web::Data<Channel>>() {
        if !channel.serving() {
            return Ok(req
                .error_response(error::ErrorServiceUnavailable(
                    "Service not available, please retry later.",
                ))
                .map_into_left_body());
        }
    }

    Ok(next.call(req).await?.map_into_right_body())
}
