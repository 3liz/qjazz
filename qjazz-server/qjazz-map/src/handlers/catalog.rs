use actix_web::{error, web, HttpRequest, HttpResponse, HttpResponseBuilder, Responder, Result};
use serde::{Deserialize, Serialize};
use std::cmp;

use crate::channel::{
    qjazz_service::{collections_page::CollectionsItem, CollectionsRequest, CollectionsType},
    Channel,
};
use crate::handlers::utils::{request, RpcResponseFactory};
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
    let public_url = request::public_url(&req, channel.route());

    let mut client = channel.client();

    let mut request = tonic::Request::new(CollectionsRequest {
        start: params.start() as i64,
        end: params.end() as i64,
        r#type: CollectionsType::Catalog.into(),
        location: None,
    });

    request.set_timeout(channel.timeout());

    match client.collections(request).await {
        Err(status) => {
            log::error!("Backend error:\t{}\t{}", channel.name(), status);
            Ok(HttpResponseBuilder::from_rpc_status(&status, None))
        }
        Ok(resp) => {
            let page = resp.into_inner();
            Ok(HttpResponse::Ok().json(Catalog {
                items: page
                    .items
                    .iter()
                    .map(|n| page_to_json(n, &public_url, false))
                    .collect::<Result<Vec<serde_json::Value>>>()?,
                links: vec![Link {
                    href: format!("{public_url}/catalog").into(),
                    rel: rel::SELF.into(),
                    r#type: mime::APPLICATION_JSON.as_ref().into(),
                    ..Default::default()
                }],
            }))
        }
    }
}

// Item handler
pub async fn item_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: web::Path<String>,
) -> Result<impl Responder> {
    let public_url = request::public_url(&req, channel.route());

    let mut client = channel.client();

    let mut request = tonic::Request::new(CollectionsRequest {
        start: 0, // Not applicable
        end: 1,   // Not applicable
        r#type: CollectionsType::Catalog.into(),
        location: Some(location.clone()),
    });

    request.set_timeout(channel.timeout());

    match client.collections(request).await {
        Err(status) => {
            log::error!("Backend error:\t{}\t{}", channel.name(), status);
            Ok(HttpResponseBuilder::from_rpc_status(&status, None))
        }
        Ok(resp) => {
            let page = resp.into_inner();
            if page.items.is_empty() {
                Ok(HttpResponse::NotFound()
                    .content_type(mime::TEXT_PLAIN)
                    .body(format!("{location} not found")))
            } else {
                Ok(HttpResponse::Ok().json(page_to_json(&page.items[0], &public_url, true)?))
            }
        }
    }
}

fn encode_name(name: &str) -> String {
    format!(
        "{}",
        percent_encoding::percent_encode(name.as_bytes(), percent_encoding::NON_ALPHANUMERIC)
    )
}

fn to_error<E: std::fmt::Debug>(e: E) -> error::Error {
    log::error!("Catalog error: {:?}", e);
    error::ErrorInternalServerError("Internal error")
}

fn page_to_json(
    item: &CollectionsItem,
    public_url: &str,
    link_self: bool,
) -> Result<serde_json::Value> {
    let mut value: serde_json::Value = serde_json::from_str(&item.json).map_err(to_error)?;
    let ident = encode_name(&item.name);

    if let Some(serde_json::Value::Array(v)) = value.get_mut("links") {
        v.reserve(if link_self { 3 } else { 2 });
        v.push(
            serde_json::to_value(Link {
                href: format!("{public_url}/catalog/{}", ident).into(),
                rel: if link_self { rel::SELF } else { rel::CHILD }.into(),
                title: Some(item.name.as_str().into()),
                r#type: mime::APPLICATION_JSON.as_ref().into(),
                ..Default::default()
            })
            .map_err(to_error)?,
        );
        v.push(
            serde_json::to_value(Link {
                href: format!("{public_url}/{}/map", ident).into(),
                rel: rel::RELATED.into(),
                r#type: mime::APPLICATION_OCTET_STREAM.as_ref().into(),
                title: Some(format!("Map for {}", item.name).into()),
                description: Some("Return a displayable map of the dataset".into()),
                ..Default::default()
            })
            .map_err(to_error)?,
        );

        if link_self {
            v.push(
                serde_json::to_value(Link {
                    href: format!("{public_url}/catalog").into(),
                    rel: rel::COLLECTION.into(),
                    r#type: mime::APPLICATION_JSON.as_ref().into(),
                    title: Some("Catalog".into()),
                    ..Default::default()
                })
                .map_err(to_error)?,
            );
        }
    }

    Ok(value)
}
