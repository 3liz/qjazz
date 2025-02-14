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
    links: [Link<'a>; 1],
    //apis: Vec<&'a ApiEndPoint>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LandingPage<'a> {
    links: [Link<'a>; 2],
}

pub async fn handler(req: HttpRequest) -> impl Responder {
    let public_url = request::public_url(&req, "");

    HttpResponse::Ok().json(LandingPage {
        links: [
            Link::application_json(format!("{public_url}/catalogs").into(), rel::API_CATALOG)
                .title("Catalog endpoints"),
            Link::application_json(format!("{public_url}{}", req.path()).into(), rel::SELF),
        ],
    })
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Catalogs<'a> {
    catalogs: Vec<ChannelItem<'a>>,
    links: [Link<'a>; 1],
}

//
// Catalogs handler
//
pub async fn catalogs(req: HttpRequest, channels: web::Data<Channels>) -> impl Responder {
    let public_url = request::public_url(&req, "");

    HttpResponse::Ok().json(Catalogs {
        catalogs: channels
            .iter()
            .map(|channel| ChannelItem {
                name: channel.name(),
                title: channel.title(),
                description: channel.description(),
                available: channel.serving(),
                //apis: channel.api_endpoints().iter().map(|n| n.get_ref()).collect(),
                links: [Link::application_json(
                    format!("{public_url}{}/catalog", channel.route()).into(),
                    rel::COLLECTION,
                )
                .title("Catalog")
                .description("Catalog of datasets from this endpoint")],
            })
            .collect(),
        links: [Link::application_json(
            format!("{public_url}{}", req.path()).into(),
            rel::SELF,
        )],
    })
}
