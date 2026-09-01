//
// Services
//
use crate::channel::Channel;
use crate::endpoint::EndPoint;
use crate::handlers::{api, catalog, conformance, landing_page, legend, map, ows};
use actix_web::{guard, http::header, web};

#[cfg(feature = "monitor")]
use actix_web::middleware;

// Configuration for api endpoint
pub fn api_scope(api: web::ThinData<EndPoint>) -> impl FnOnce(&mut web::ServiceConfig) {
    let path = format!("/{}", api.endpoint());

    let scope = web::scope(path.as_str())
        .app_data(api.clone())
        .route("{path:.*}", web::to(api::handler))
        .default_service(web::to(api::default_handler));

    move |cfg| {
        cfg.service(scope)
            .service(
                web::resource(format!("{path}.json").as_str())
                    .app_data(api.clone())
                    .to(api::default_handler),
            )
            .service(
                web::resource(format!("{path}.html").as_str())
                    .app_data(api.clone())
                    .to(api::default_handler),
            );
    }
}

// Configuration for handling OWS resources
pub fn ows_resource(cfg: &mut web::ServiceConfig) {
    #[cfg(feature = "monitor")]
    let resource = web::resource("").wrap(middleware::from_fn(crate::monitor::middleware));

    #[cfg(not(feature = "monitor"))]
    let resource = web::resource("");

    cfg.service(
        resource
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

// Landing page
pub fn landing_page(channels: Vec<web::Data<Channel>>) -> impl FnOnce(&mut web::ServiceConfig) {
    move |cfg| {
        cfg.route("/", web::get().to(landing_page::handler))
            .service(
                web::resource("/catalogs")
                    .app_data(web::Data::new(channels))
                    .get(landing_page::catalogs),
            );
    }
}

//
// Catalog
//
//
pub fn catalog(cfg: &mut web::ServiceConfig) {
    cfg.route("/catalog", web::get().to(catalog::catalog_handler))
        .service(
            web::scope("/catalog/{id}")
                .default_service(web::get().to(catalog::item_handler))
                .configure(default_map)
                .configure(maps)
                .route("/conformance", web::get().to(conformance::handler)),
        );
}

// GET or FORM Resource build helper
fn get_form_resource<F, Args>(path: &str, handler: F) -> actix_web::Resource
where
    F: actix_web::Handler<Args> + Clone,
    F::Output: actix_web::Responder + 'static,
    Args: actix_web::FromRequest + 'static,
{
    // Take care to check only Mime type essence
    web::resource(path).get(handler.clone()).route(
        web::post()
            .guard(guard::fn_guard(|ctx| {
                ctx.head()
                    .headers()
                    .get(header::CONTENT_TYPE)
                    .and_then(|v| v.to_str().ok())
                    .and_then(|v| v.parse::<mime::Mime>().ok())
                    .is_some_and(|m| m.essence_str() == "application/x-www-form-urlencoded")
            }))
            .to(handler),
    )
}

//
// OGG api 'Map' services
//
//
pub fn default_map(cfg: &mut web::ServiceConfig) {
    cfg.service(get_form_resource("/map", map::default_handler));
}

pub fn maps(cfg: &mut web::ServiceConfig) {
    cfg.route("/maps", web::get().to(catalog::collections_handler))
        .service(
            web::scope("/maps/{res}")
                .default_service(web::get().to(catalog::collections_item_handler))
                .configure(collection_map),
        );
}

//
// /map for dataset child item (layer)
//
pub fn collection_map(cfg: &mut web::ServiceConfig) {
    cfg.service(get_form_resource("/map", map::child_handler))
        .route("/legend", web::get().to(legend::default_handler))
        .route(
            "/styles/{style}/legend",
            web::get().to(legend::styled_handler),
        )
        .service(get_form_resource(
            "/styles/{style}/map",
            map::styled_child_handler,
        ));
}
