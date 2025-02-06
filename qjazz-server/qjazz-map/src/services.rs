//
// Services
//
use crate::channel::Channel;
use crate::handlers::{api, catalog, landing_page, map, ows};
use crate::resolver::ApiEndPoint;
use actix_web::{guard, web};

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
pub fn ows_resource(cfg: &mut web::ServiceConfig) {
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

// Landing page
pub fn landing_page(channels: Vec<web::Data<Channel>>) -> impl FnOnce(&mut web::ServiceConfig) {
    move |cfg| {
        cfg.service(
            web::resource("/")
                .app_data(web::Data::new(channels))
                .get(landing_page::handler),
        );
    }
}

// Catalog
pub fn catalog(cfg: &mut web::ServiceConfig) {
    cfg.route("/catalog", web::get().to(catalog::catalog_handler))
        .service(
            web::scope("/catalog/{id}")
                .default_service(web::get().to(catalog::item_handler))
                .configure(default_map)
                .route("/maps", web::get().to(catalog::collections_handler))
                .route(
                    "/maps/{res}",
                    web::get().to(catalog::collections_item_handler),
                ),
        );
}

// OGG api 'Map' services
pub fn default_map(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::resource("/map").get(map::handler).route(
            web::post()
                .guard(guard::Header(
                    "content-type",
                    "application/x-www-form-urlencoded",
                ))
                .to(map::handler),
        ),
    )
    .service(
        web::resource("/maps/{res}/map")
            .get(map::collection_handler)
            .route(
                web::post()
                    .guard(guard::Header(
                        "content-type",
                        "application/x-www-form-urlencoded",
                    ))
                    .to(map::collection_handler),
            ),
    );
}
