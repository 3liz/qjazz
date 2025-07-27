//
// Services
//
use crate::channel::Channel;
use crate::handlers::{api, catalog, conformance, landing_page, legend, map, ows};
use crate::resolver::ApiEndPoint;
use actix_web::{guard, web};

#[cfg(feature = "monitor")]
use actix_web::middleware;

// Configuration for api endpoint
pub fn api_scope(api: web::Data<ApiEndPoint>) -> impl FnOnce(&mut web::ServiceConfig) {
    let path = format!("/{}", api.endpoint);

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

//
// OGG api 'Map' services
//
//
pub fn default_map(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::resource("/map").get(map::default_handler).route(
            web::post()
                .guard(guard::Header(
                    "content-type",
                    "application/x-www-form-urlencoded",
                ))
                .to(map::default_handler),
        ),
    );
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
    cfg.service(
        web::resource("/map").get(map::child_handler).route(
            web::post()
                .guard(guard::Header(
                    "content-type",
                    "application/x-www-form-urlencoded",
                ))
                .to(map::child_handler),
        ),
    )
    .route("/legend", web::get().to(legend::default_handler))
    .route(
        "/styles/{style}/legend",
        web::get().to(legend::styled_handler),
    )
    .service(
        web::resource("/styles/{style}/map")
            .get(map::styled_child_handler)
            .route(
                web::post()
                    .guard(guard::Header(
                        "content-type",
                        "application/x-www-form-urlencoded",
                    ))
                    .to(map::styled_child_handler),
            ),
    );
}
