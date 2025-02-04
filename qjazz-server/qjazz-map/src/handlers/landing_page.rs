use actix_web::{web, HttpRequest, HttpResponse, Responder};
use serde::Serialize;

use crate::channel::Channel;
use crate::handlers::utils::request;
use crate::models::{rel, Link};

type Channels = Vec<web::Data<Channel>>;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ChannelItem<'a> {
    name: &'a str,
    title: &'a str,
    description: &'a str,
    available: bool,
    links: Vec<Link<'a>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LandingPage<'a> {
    endpoints: Vec<ChannelItem<'a>>,
    links: Vec<Link<'a>>,
}

// Landing page handler
pub async fn handler(req: HttpRequest, channels: web::Data<Channels>) -> impl Responder {
    let public_url = request::public_url(&req, "");

    HttpResponse::Ok().json(LandingPage {
        endpoints: channels
            .iter()
            .map(|channel| ChannelItem {
                name: channel.name(),
                title: channel.title(),
                description: channel.description(),
                available: channel.serving(),
                links: vec![Link {
                    href: format!("{public_url}{}/catalog", channel.route()).into(),
                    rel: rel::RELATED.into(),
                    r#type: mime::APPLICATION_JSON.as_ref().into(),
                    title: Some("Catalog".into()),
                    description: Some("Catalog of datasets from this endpoint".into()),
                    ..Default::default()
                }],
            })
            .collect(),
        links: vec![Link {
            href: format!("{public_url}{}", req.path()).into(),
            rel: rel::SELF.into(),
            r#type: mime::APPLICATION_JSON.as_ref().into(),
            ..Default::default()
        }],
    })
}
