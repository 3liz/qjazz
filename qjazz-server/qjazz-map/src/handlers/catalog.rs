//
// Catalog handler
//
use actix_web::{error, web, HttpRequest, HttpResponse, Responder, Result};
use serde::{Deserialize, Serialize};
use std::cmp;

use crate::channel::{
    qjazz_service::{collections_page::CollectionsItem, CollectionsRequest},
    Channel,
};
use crate::handlers::response::RpcHttpResponseBuilder;
use crate::handlers::utils::request;
use crate::models::apis::OgcEndpoints;
use crate::models::{rel, Link};

const MAX_PAGE_LIMIT: u16 = 50;

#[derive(Deserialize)]
#[serde(default)]
pub struct Params {
    page: u16,
    limit: u16,
}

impl Default for Params {
    fn default() -> Self {
        Self {
            page: 0,
            limit: MAX_PAGE_LIMIT,
        }
    }
}

impl Params {
    fn start(&self) -> u16 {
        self.page * cmp::min(self.limit, MAX_PAGE_LIMIT)
    }
    fn end(&self) -> u16 {
        self.start() + cmp::min(self.limit, MAX_PAGE_LIMIT)
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Catalog<'a> {
    items: Vec<serde_json::Value>,
    links: Vec<Link<'a>>,
}

// Catalog handler
pub async fn catalog_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    params: web::Query<Params>,
) -> Result<impl Responder> {
    collection_request(
        req,
        channel,
        params,
        None,
        None,
        |item, links, public_url| {
            let item_url = item_url(item, public_url);
            links
                .reserve(2)
                .add(
                    Link::application_json((&item_url).into(), rel::OGC_REL_ITEM)
                        .title(item.name.as_str()),
                )?
                .add(
                    Link::new(format!("{item_url}/map").into(), rel::OGC_REL_MAP)
                        .title("Default map"),
                )?;
            Ok(())
        },
    )
    .await
}

// Collections handler
// Return the collection (layers) of a catalog entry
pub async fn collections_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    params: web::Query<Params>,
    location: web::Path<String>,
) -> Result<impl Responder> {
    collection_request(
        req,
        channel,
        params,
        Some(location.into_inner()),
        None,
        |item, links, public_url| {
            let item_url = item_url(item, &public_url);
            let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);
            links.reserve(2).add(
                Link::application_json((&item_url).into(), rel::OGC_REL_ITEM)
                    .title(item.name.as_str()),
            )?;
            if endpoints.contains(OgcEndpoints::MAP) {
                links.add(
                    Link::new(format!("{item_url}/map").into(), rel::OGC_REL_MAP)
                        .title("Default map"),
                )?;
            }
            Ok(())
        },
    )
    .await
}

async fn collection_request<F>(
    req: HttpRequest,
    channel: web::Data<Channel>,
    params: web::Query<Params>,
    location: Option<String>,
    resource: Option<String>,
    mut with_links: F,
) -> Result<impl Responder>
where
    F: FnMut(&CollectionsItem, &mut Links, &str) -> Result<()>,
{
    let public_url = request::location(&req);

    let mut client = channel.client();

    let mut request = tonic::Request::new(CollectionsRequest {
        start: params.start() as i64,
        end: params.end() as i64,
        location,
        resource,
    });

    request.set_timeout(channel.timeout());

    match client.collections(request).await {
        Err(status) => {
            log::error!("Backend error:\t{}\t{}", channel.name(), status);
            Ok(RpcHttpResponseBuilder::from_rpc_status(&status, None))
        }
        Ok(resp) => {
            let page = resp.into_inner();
            Ok(HttpResponse::Ok().json(Catalog {
                items: page
                    .items
                    .iter()
                    .map(|n| {
                        let mut page = JsonPage::from_item(n)?;
                        if let Some(mut links) = page.links() {
                            with_links(n, &mut links, &public_url)?;
                        }
                        Ok(page.into_value())
                    })
                    .collect::<Result<Vec<serde_json::Value>>>()?,
                links: vec![Link::application_json(public_url.into(), rel::SELF)],
            }))
        }
    }
}

// Handler from catalog item
pub async fn item_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resource: web::Path<String>,
) -> Result<impl Responder> {
    item_request(
        req,
        channel,
        None,
        Some(resource.into_inner()),
        |item, links, public_url| {
            links
                .reserve(3)
                .add(
                    Link::application_json((public_url).into(), rel::SELF)
                        .title(item.name.as_str()),
                )?
                .add(
                    Link::new(format!("{public_url}/map").into(), rel::OGC_REL_MAP)
                        .title("Default map"),
                )?
                .add(
                    Link::new(format!("{public_url}/maps").into(), rel::OGC_REL_DATA).title("Maps"),
                )?;
            Ok(())
        },
    )
    .await
}

pub async fn collections_item_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resources: web::Path<(String, String)>,
) -> Result<impl Responder> {
    let (location, resource) = resources.into_inner();
    item_request(
        req,
        channel,
        Some(location),
        Some(resource),
        |item, links, public_url| {
            let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);
            links.reserve(2).add(
                Link::application_json((public_url).into(), rel::SELF).title(item.name.as_str()),
            )?;
            if endpoints.contains(OgcEndpoints::MAP) {
                links.add(
                    Link::new(format!("{public_url}/map").into(), rel::OGC_REL_MAP)
                        .title("Default map"),
                )?;
            }
            Ok(())
        },
    )
    .await
}

// Item handler
pub async fn item_request<F>(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: Option<String>,
    resource: Option<String>,
    mut with_links: F,
) -> Result<impl Responder>
where
    F: FnMut(&CollectionsItem, &mut Links, &str) -> Result<()>,
{
    let public_url = request::location(&req);

    let mut client = channel.client();

    let mut request = tonic::Request::new(CollectionsRequest {
        start: 0, // Not applicable
        end: 1,   // Not applicable
        location,
        resource,
    });

    request.set_timeout(channel.timeout());

    match client.collections(request).await {
        Err(status) => {
            log::error!("Backend error:\t{}\t{}", channel.name(), status);
            Ok(RpcHttpResponseBuilder::from_rpc_status(&status, None))
        }
        Ok(resp) => {
            let page = resp.into_inner();
            if page.items.is_empty() {
                Ok(HttpResponse::NotFound()
                    .content_type(mime::TEXT_PLAIN)
                    .body(format!("Resource not found")))
            } else {
                Ok(HttpResponse::Ok().json({
                    let item = &page.items[0];
                    let mut page = JsonPage::from_item(item)?;
                    if let Some(mut links) = page.links() {
                        with_links(item, &mut links, &public_url)?;
                    }
                    page.into_value()
                }))
            }
        }
    }
}

fn item_url(item: &CollectionsItem, public_url: &str) -> String {
    format!(
        "{public_url}/{}",
        percent_encoding::percent_encode(&item.name.as_bytes(), percent_encoding::NON_ALPHANUMERIC),
    )
}

fn to_error<E: std::fmt::Debug>(e: E) -> error::Error {
    log::error!("Catalog error: {:?}", e);
    error::ErrorInternalServerError("Internal error")
}

struct JsonPage(serde_json::Value);

impl JsonPage {
    fn from_item(item: &CollectionsItem) -> Result<Self> {
        serde_json::from_str(&item.json)
            .map_err(to_error)
            .map(|v| Self(v))
    }

    fn into_value(self) -> serde_json::Value {
        self.0
    }

    fn links(&mut self) -> Option<Links> {
        if let Some(serde_json::Value::Array(v)) = self.0.get_mut("links") {
            Some(Links(v))
        } else {
            None
        }
    }
}

struct Links<'a>(&'a mut Vec<serde_json::Value>);

impl<'a> Links<'a> {
    fn reserve(&mut self, additional: usize) -> &mut Self {
        self.0.reserve(additional);
        self
    }

    fn add(&mut self, link: Link) -> Result<&mut Self> {
        self.0.push(serde_json::to_value(link).map_err(to_error)?);
        Ok(self)
    }
}
