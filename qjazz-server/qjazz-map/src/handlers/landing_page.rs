use actix_web::{web, HttpRequest, HttpResponse, Responder};
use serde::Serialize;

use crate::channel::Channel;
use crate::handlers::utils::request;
use crate::models::{rel, Link};
//use crate::resolver::ApiEndPoint;

type Channels = Vec<web::Data<Channel>>;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ChannelItem<'a> {
    name: &'a str,
    title: &'a str,
    description: &'a str,
    available: bool,
    links: Vec<Link<'a>>,
    //apis: Vec<&'a ApiEndPoint>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LandingPage<'a> {
    catalogs: Vec<ChannelItem<'a>>,
    links: Vec<Link<'a>>,
}

// Landing page handler
pub async fn handler(req: HttpRequest, channels: web::Data<Channels>) -> impl Responder {
    let public_url = request::public_url(&req, "");

    HttpResponse::Ok().json(LandingPage {
        catalogs: channels
            .iter()
            .map(|channel| ChannelItem {
                name: channel.name(),
                title: channel.title(),
                description: channel.description(),
                available: channel.serving(),
                //apis: channel.api_endpoints().iter().map(|n| n.get_ref()).collect(),
                links: vec![Link::application_json(
                    format!("{public_url}{}/catalog", channel.route()).into(),
                    rel::COLLECTION,
                )
                .title("Catalog")
                .description("Catalog of datasets from this endpoint")],
            })
            .collect(),
        links: vec![Link::application_json(
            format!("{public_url}{}", req.path()).into(),
            rel::SELF,
        )],
    })
}
