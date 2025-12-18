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
            //.default_service(web::get(api::landing_page));
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
}
