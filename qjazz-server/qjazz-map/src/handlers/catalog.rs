//
// Catalog handler
//
use actix_web::{Either, HttpRequest, HttpResponse, Responder, Result, error, web};
use serde::{Deserialize, Serialize};
use std::borrow::Cow;
use std::cmp;

use crate::channel::{
    Channel,
    qjazz_service::{CollectionsPage, CollectionsRequest, collections_page::CollectionsItem},
};
use crate::handlers::response;
use crate::models::apis::OgcEndpoints;
use crate::models::{Link, rel};
use crate::requests::request;

const MAX_PAGE_LIMIT: u64 = 50;

//
// Handle page parameters
//
#[derive(Deserialize)]
#[serde(default)]
pub struct Params {
    page: u64,
    limit: u64,
    prefix: Option<String>,
}

impl Default for Params {
    fn default() -> Self {
        Self {
            page: 1, // Pages start at 1
            limit: MAX_PAGE_LIMIT,
            prefix: None,
        }
    }
}

impl Params {
    fn limit(&self) -> u64 {
        cmp::min(self.limit, MAX_PAGE_LIMIT)
    }
    fn start(&self) -> u64 {
        self.page.saturating_sub(1).saturating_mul(self.limit())
    }
    fn end(&self) -> u64 {
        self.start().saturating_add(self.limit())
    }
    #[inline]
    fn range(&self) -> std::ops::Range<i64> {
        (self.start().clamp(0, u64::MAX >> 1) as i64)..(self.end().clamp(0, u64::MAX >> 1) as i64)
    }
    // Create navigation links
    fn links(&self, links: &mut Vec<Link>, public_url: &str, next: bool) {
        let limit = self.limit();

        links.reserve(3);
        links.push(Link::application_json(
            format!("{public_url}?page={}&limit={limit}", self.page).into(),
            rel::SELF,
        ));
        if next {
            links.push(Link::application_json(
                format!("{public_url}?page={}&limit={limit}", self.page + 1).into(),
                rel::NEXT,
            ));
        }
        if self.page > 1 {
            links.push(Link::application_json(
                format!("{public_url}?page={}&limit={limit}", self.page - 1).into(),
                rel::PREV,
            ));
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Collections<'a> {
    collections: Vec<serde_json::Value>,
    links: Vec<Link<'a>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Catalog<'a> {
    links: Vec<Link<'a>>,
}

const PREFIX_END: char = '/';

// Catalog handler
pub async fn catalog_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    mut params: web::Query<Params>,
) -> Result<impl Responder> {
    if channel.disable_root_catalog() {
        // Return a 403 http response
        return Ok(
            HttpResponse::Forbidden().body("Catalog listing has been disabled for this channel")
        );
    }

    // Add mandatory terminaison for location prefix
    let prefix = params.prefix.take().map(|mut s| {
        if !s.ends_with(PREFIX_END) {
            s.push(PREFIX_END)
        }
        s
    });

    match execute_collection_request(channel.as_ref(), prefix, None, params.range()).await {
        Either::Left(resp) => Ok(resp),
        Either::Right(page) => {
            let public_url = request::location(&req);
            let mut links = Vec::with_capacity(page.items.len());

            for item in &page.items {
                let item_url = item_url(item, &public_url);
                let mut js = JsonPage::from_item(item)?;
                let mut link = Link::application_json(item_url.into(), rel::ITEM);

                link.title = js.get_into_string("title").map(Cow::from);
                link.description = js.get_into_string("description").map(Cow::from);
                links.push(link);
            }
            // Add navigation links
            params.links(&mut links, &public_url, page.next);
            Ok(HttpResponse::Ok().json(Catalog { links }))
        }
    }
}

pub async fn collections_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    params: web::Query<Params>,
    location: web::Path<String>,
) -> Result<impl Responder> {
    match execute_collection_request(
        channel.as_ref(),
        Some(location.into_inner()),
        None,
        params.range(),
    )
    .await
    {
        Either::Left(resp) => Ok(resp),
        Either::Right(page) => {
            let public_url = request::location(&req);
            let mut links = Vec::new();
            // Add navigation links
            params.links(&mut links, &public_url, page.next);

            Ok(HttpResponse::Ok().json(Collections {
                collections: page
                    .items
                    .iter()
                    .map(|item| {
                        let mut page = JsonPage::from_item(item)?;

                        let item_url = item_url(item, &public_url);
                        let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);

                        page.add_ogc_endpoints(&item_url, endpoints)?;
                        page.add_legend_links(&item_url)?;

                        let mut links = page.links()?;
                        links.add(
                            Link::application_json((&item_url).into(), rel::OGC_REL_ITEM)
                                .title(item.name.as_str()),
                        )?;

                        Ok(page.into_value())
                    })
                    .collect::<Result<Vec<serde_json::Value>>>()?,
                links,
            }))
        }
    }
}

// Handler from catalog item (project)
pub async fn item_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resource: web::Path<String>,
) -> Result<impl Responder> {
    match execute_collection_request(channel.as_ref(), None, Some(resource.into_inner()), 0..1)
        .await
    {
        Either::Left(resp) => Ok(resp),
        Either::Right(page) => {
            let public_url = request::location(&req);
            if page.items.is_empty() {
                Ok(HttpResponse::NotFound()
                    .content_type(mime::TEXT_PLAIN)
                    .body("Resource not found"))
            } else {
                Ok(HttpResponse::Ok().json({
                    let item = &page.items[0];
                    let mut js_item = JsonPage::from_item(item)?;
                    js_item
                        .links()?
                        .reserve(4)
                        .add(
                            Link::application_json((&public_url).into(), rel::SELF)
                                .title(item.name.as_str()),
                        )?
                        .add(
                            Link::new(format!("{public_url}/map").into(), rel::OGC_REL_MAP)
                                .title("Default map"),
                        )?
                        .add(
                            Link::application_json(
                                format!("{public_url}/maps").into(),
                                rel::OGC_REL_DATA,
                            )
                            .title("Maps"),
                        )?
                        .add(
                            Link::application_json(
                                format!("{public_url}/conformance").into(),
                                rel::CONFORMANCE,
                            )
                            .title("OGC API conformance classes"),
                        )?;
                    js_item.into_value()
                }))
            }
        }
    }
}

// Handler for sub items of catalog (i.e layers)
pub async fn collections_item_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resources: web::Path<(String, String)>,
) -> Result<impl Responder> {
    let (location, resource) = resources.into_inner();

    match execute_collection_request(channel.as_ref(), Some(location), Some(resource), 0..1).await {
        Either::Left(resp) => Ok(resp),
        Either::Right(page) => {
            let public_url = request::location(&req);
            if page.items.is_empty() {
                Ok(HttpResponse::NotFound()
                    .content_type(mime::TEXT_PLAIN)
                    .body("Resource not found"))
            } else {
                Ok(HttpResponse::Ok().json({
                    let item = &page.items[0];
                    let mut js_item = JsonPage::from_item(item)?;

                    let endpoints = OgcEndpoints::from_bits_retain(item.endpoints);
                    js_item.add_ogc_endpoints(&public_url, endpoints)?;
                    js_item.add_legend_links(&public_url)?;

                    let mut links = js_item.links()?;
                    links.add(
                        Link::application_json((&public_url).into(), rel::SELF)
                            .title(item.name.as_str()),
                    )?;

                    js_item.into_value()
                }))
            }
        }
    }
}

async fn execute_collection_request(
    channel: &Channel,
    location: Option<String>,
    resource: Option<String>,
    range: std::ops::Range<i64>,
) -> Either<HttpResponse, CollectionsPage> {
    let mut client = channel.client();
    let mut request = tonic::Request::new(CollectionsRequest {
        start: range.start,
        end: range.end,
        location,
        resource,
    });
    request.set_timeout(channel.timeout());

    match client.collections(request).await {
        Ok(resp) => Either::Right(resp.into_inner()),
        Err(status) => {
            log::error!("Backend error:\t{}\t{}", channel.name(), status);
            Either::Left(response::from_rpc_status(&status, None))
        }
    }
}

fn item_url(item: &CollectionsItem, public_url: &str) -> String {
    format!(
        "{public_url}/{}",
        percent_encoding::percent_encode(item.name.as_bytes(), percent_encoding::NON_ALPHANUMERIC),
    )
}

fn internal_error<E: std::fmt::Debug>(e: E) -> error::Error {
    log::error!("Catalog error: {e:?}");
    error::ErrorInternalServerError("Internal error")
}

struct JsonPage(serde_json::Map<String, serde_json::Value>);

impl JsonPage {
    const STYLE: &str = "styles";

    fn from_item(item: &CollectionsItem) -> Result<Self> {
        serde_json::from_str(&item.json)
            .map_err(internal_error)
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
        // NOTE: Only MAP is implemented
        //
        // Implementing FEATURE need to implement link to a WFS3/FEATURE api
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

    fn links(&mut self) -> Result<Links<'_>> {
        static LINKS: &str = "links";
        if !self.0.contains_key(LINKS) {
            self.0
                .insert(LINKS.into(), serde_json::Value::Array(Vec::new()));
        }

        // A `links` entry MUST be a array
        if let Some(serde_json::Value::Array(v)) = self.0.get_mut(LINKS) {
            Ok(Links(v))
        } else {
            log::warn!("No 'links' array found in json object");
            Err(error::ErrorInternalServerError("Internal error"))
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
        self.0
            .push(serde_json::to_value(link).map_err(internal_error)?);
        Ok(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn params(query: &str) -> web::Query<Params> {
        web::Query::<Params>::from_query(query).unwrap()
    }

    #[test]
    fn test_pagination_overflow() {
        // A page index large enough to overflow `page * limit` must saturate
        // instead of panicking (debug) or wrapping around (release).
        let p = params(&format!("page={}&limit={MAX_PAGE_LIMIT}", u64::MAX));
        assert_eq!(p.range(), i64::MAX..i64::MAX);

        // Same for `start + limit` when the start is already at the boundary.
        let p = params(&format!("page=1&limit={}", u64::MAX));
        assert_eq!(p.limit(), MAX_PAGE_LIMIT);
        assert_eq!(p.range(), 0..(MAX_PAGE_LIMIT as i64));
    }
}
