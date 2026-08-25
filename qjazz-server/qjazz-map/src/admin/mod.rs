//
// Admin services
//
// Configuration for admin api

use actix_web::{guard, web};

use crate::channel::Channel;

mod catalog;
mod plugins;
mod projects;

pub fn admin(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::scope("/admin")
            .guard(guard::fn_guard(|ctx| {
                ctx.app_data::<web::Data<Channel>>()
                    .map(|channel| channel.admin())
                    .unwrap_or(false)
            }))
            .default_service(web::get().to(api::landing_page))
            .service(web::resource("/catalog").get(api::catalog))
            .service(web::resource("/catalog{Path:/.*}").get(api::catalog_with))
            .service(web::resource("/plugins").get(api::plugins))
            .service(
                web::resource("/projects")
                    .post(api::pull_projects)
                    .get(api::get_projects)
                    .delete(api::delete_projects),
            )
            .service(
                web::resource("/projects{Path:/.+}")
                    .get(api::get_project_with)
                    .delete(api::delete_project_with),
            ),
    );
}

mod api {
    pub use super::catalog::{catalog, catalog_with};
    pub use super::plugins::plugins;
    pub use super::projects::{
        delete_project_with, delete_projects, get_project_with, get_projects, pull_projects,
    };

    use actix_web::{HttpRequest, HttpResponse, Responder};
    use serde::Serialize;

    use crate::models::{Link, rel};
    use crate::requests::request;

    #[derive(Debug, Serialize)]
    #[serde(rename_all = "camelCase")]
    struct LandingPage<'a> {
        links: [Link<'a>; 4],
    }

    // Admin entry points
    pub async fn landing_page(req: HttpRequest) -> impl Responder {
        let public_url = request::public_url(&req, "");

        HttpResponse::Ok().json(LandingPage {
            links: [
                Link::application_json(format!("{public_url}{}", req.path()).into(), rel::SELF),
                Link::application_json(
                    format!("{public_url}{}/plugins", req.path()).into(),
                    rel::CHILDREN,
                )
                .title("Installed Plugins"),
                Link::application_json(
                    format!("{public_url}{}/catalog", req.path()).into(),
                    rel::CHILDREN,
                )
                .title("Project's catalog")
                .description("List available projects"),
                Link::application_json(
                    format!("{public_url}{}/projects", req.path()).into(),
                    rel::CHILDREN,
                )
                .title("Project's cache")
                .description("List pinned projects in cache"),
            ],
        })
    }
}
