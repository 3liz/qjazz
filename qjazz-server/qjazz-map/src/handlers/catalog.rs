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
    #[inline]
    fn next_page(&self) -> u16 {
        self.page + 1    
    }
    #[inline]
    fn prev_page(&self) -> u16 {
        if self.page > 0 { self.page - 1 } else { 0 }
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
        |item, page, public_url| {
            let item_url = item_url(item, public_url);
            page.links()?
                .reserve(4)
                .add(
                    Link::application_json((&item_url).into(), rel::CHILD)
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
        |item, page, public_url| {
            let item_url = item_url(item, public_url);
            let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);
            page.add_ogc_endpoints(&item_url, endpoints)?;
            page.add_legend_links(&item_url)?;
            let mut links = page.links()?;
            links.add(
                Link::application_json((&item_url).into(), rel::OGC_REL_ITEM)
                    .title(item.name.as_str()),
            )?;
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
    mut with_page: F,
) -> Result<impl Responder>
where
    F: FnMut(&CollectionsItem, &mut JsonPage, &str) -> Result<()>,
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
            let mut links = Vec::with_capacity(3);
            links.push(Link::application_json(
                format!(
                    "{public_url}?page={}&limit={}",
                        params.page,
                        params.limit,
                    ).into(),
                    rel::SELF
            ));
            if page.next {
                links.push(Link::application_json(
                    format!("{public_url}?page={}&limit={}",
                        params.next_page(),
                        params.limit,
                    ).into(),
                    rel::NEXT,
                ));
            }
            if params.page > 0 {
                 links.push(Link::application_json(
                    format!("{public_url}?page={}&limit={}",
                        params.prev_page(),
                        params.limit,
                    ).into(),
                    rel::PREV,
                ));
                                
            }

            Ok(HttpResponse::Ok().json(Catalog {
                items: page
                    .items
                    .iter()
                    .map(|n| {
                        let mut page = JsonPage::from_item(n)?;
                        with_page(n, &mut page, &public_url)?;
                        Ok(page.into_value())
                    })
                    .collect::<Result<Vec<serde_json::Value>>>()?,
                links,
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
        |item, page, public_url| {
            page.links()?
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

// Handler for sub items of catalog (i.e layers)
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
        |item, page, public_url| {
            let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);
            page.add_ogc_endpoints(&public_url, endpoints)?;
            page.add_legend_links(public_url)?;
            let mut links = page.links()?;
            links.add(
                Link::application_json((public_url).into(), rel::SELF).title(item.name.as_str()),
            )?;
            Ok(())
        },
    )
    .await
}

// Item handler
async fn item_request<F>(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: Option<String>,
    resource: Option<String>,
    mut with_page: F,
) -> Result<impl Responder>
where
    F: FnMut(&CollectionsItem, &mut JsonPage, &str) -> Result<()>,
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
                    .body("Resource not found"))
            } else {
                Ok(HttpResponse::Ok().json({
                    let item = &page.items[0];
                    let mut json_page = JsonPage::from_item(item)?;
                    with_page(item, &mut json_page, &public_url)?;
                    json_page.into_value()
                }))
            }
        }
    }
}

fn item_url(item: &CollectionsItem, public_url: &str) -> String {
    format!(
        "{public_url}/{}",
        percent_encoding::percent_encode(item.name.as_bytes(), percent_encoding::NON_ALPHANUMERIC),
    )
}

fn to_error<E: std::fmt::Debug>(e: E) -> error::Error {
    log::error!("Catalog error: {:?}", e);
    error::ErrorInternalServerError("Internal error")
}

struct JsonPage(serde_json::Map<String, serde_json::Value>);

impl JsonPage {
    const STYLE: &str = "styles";

    fn from_item(item: &CollectionsItem) -> Result<Self> {
        serde_json::from_str(&item.json)
            .map_err(to_error)
            .and_then(|v| match v {
                serde_json::Value::Object(m) => Ok(Self(m)),
                _ => Err(error::ErrorInternalServerError(
                    "Expecting JSon object from collection",
                )),
            })
    }

    fn into_value(self) -> serde_json::Value {
        serde_json::Value::Object(self.0)
    }

    fn get_into_string(&mut self, name: &str) -> Option<String> {
        if let Some(serde_json::Value::String(s)) = self.0.remove(name) {
            Some(s)
        } else {
            None
        }
    }

    fn has_styles(&self) -> bool {
        self.0.contains_key(Self::STYLE)
    }

    // Handle OGC endpoints for child item (layer)
    fn add_ogc_endpoints(&mut self, public_url: &str, endpoints: OgcEndpoints) -> Result<()> {
        let styled = self.has_styles();
        let mut links = self.links()?;
        if endpoints.contains(OgcEndpoints::MAP) {
            links.reserve(2).add(
                Link::new(format!("{public_url}/map").into(), rel::OGC_REL_MAP)
                    .title("Default map"),
            )?;
            if styled {
                links.add(
                    Link::new(
                        format!("{public_url}/styles/{{style}}/map").into(),
                        rel::OGC_REL_MAP,
                    )
                    .title("Styled map")
                    .templated(),
                )?;
            }
        }
        Ok(())
    }

    fn add_legend_links(&mut self, public_url: &str) -> Result<()> {
        let legend_url = self.get_into_string("legendUrl");
        let legend_fmt = self.get_into_string("legendUrlFormat");

        let styled = legend_url.is_none() && self.has_styles();

        let mut links = self.links()?;
        links.reserve(2).add(
            Link::new(
                legend_url
                    .unwrap_or_else(|| format!("{public_url}/legend"))
                    .into(),
                rel::OGC_REL_LEGEND,
            )
            .media_type(legend_fmt.as_deref().unwrap_or(mime::IMAGE_PNG.as_ref()))
            .title("Default legend"),
        )?;
        if styled {
            links.add(
                Link::new(
                    format!("{public_url}/styles/{{style}}/legend").into(),
                    rel::OGC_REL_LEGEND,
                )
                .media_type(legend_fmt.as_deref().unwrap_or(mime::IMAGE_PNG.as_ref()))
                .title("Styled legend")
                .templated(),
            )?;
        }
        Ok(())
    }

    fn links(&mut self) -> Result<Links> {
        if let Some(serde_json::Value::Array(v)) = self.0.get_mut("links") {
            Ok(Links(v))
        } else {
            Err(error::ErrorInternalServerError(
                "No 'links' array found in json object",
            ))
        }
    }
}

struct Links<'a>(&'a mut Vec<serde_json::Value>);

impl Links<'_> {
    fn reserve(&mut self, additional: usize) -> &mut Self {
        self.0.reserve(additional);
        self
    }

    fn add(&mut self, link: Link) -> Result<&mut Self> {
        self.0.push(serde_json::to_value(link).map_err(to_error)?);
        Ok(self)
    }
}
