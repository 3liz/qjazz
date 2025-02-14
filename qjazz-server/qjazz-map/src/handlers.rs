use crate::channel::{ApiEndPoint, Channel};
use actix_web::{http, web, HttpRequest, HttpResponse, Responder};
use serde::Deserialize;

pub mod catalog;
pub mod conformance;
pub mod landing_page;
pub mod legend;
pub mod map;
pub mod response;
pub mod utils;

use crate::channel::qjazz_service::{ApiRequest, OwsRequest};
use response::{metadata, StreamedResponse};
use utils::request;

//
// Ows handler
//

pub mod ows {

    use super::*;

    #[derive(Deserialize)]
    pub struct Ows {
        #[serde(alias = "service", alias = "Service", alias = "SERVICE")]
        service: String, // Required
        #[serde(alias = "request", alias = "Request", alias = "REQUEST")]
        request: Option<String>,
        #[serde(alias = "version", alias = "Version", alias = "VERSION")]
        version: Option<String>,
        #[serde(alias = "map", alias = "Map", alias = "MAP")]
        map: Option<String>,
    }

    async fn ows_response(
        req: HttpRequest,
        channel: web::Data<Channel>,
        args: Ows,
        data: web::Bytes,
    ) -> impl Responder {
        let mut client = channel.client();

        let request_id = request::request_id(&req).map(String::from);
        let content_type =
            request::header_as_str(&req, http::header::CONTENT_TYPE).map(String::from);

        let data = data.to_vec();

        let mut request = tonic::Request::new(OwsRequest {
            service: args.service,
            request: args.request.unwrap_or_default(),
            version: args.version,
            target: args.map.unwrap_or_default(),
            url: Some(request::location(&req)),
            direct: channel.allow_direct_resolution(),
            options: Some(req.query_string().to_string()),
            method: Some(req.method().as_str().to_string()),
            body: (!data.is_empty()).then_some(data),
            request_id: request_id.clone(),
            content_type,
        });

        request.set_timeout(channel.timeout());

        // forward headers
        metadata::insert_from_headers(request.metadata_mut(), req.headers(), |h| {
            channel.allow_header(h)
        });

        StreamedResponse::new(
            client.execute_ows_request(request).await,
            channel.name(),
            request_id,
        )
        .into_response(channel)
    }

    // Handle request with query arguments
    #[inline]
    pub async fn query_handler(
        req: HttpRequest,
        channel: web::Data<Channel>,
        args: web::Query<Ows>,
        bytes: web::Bytes,
    ) -> impl Responder {
        ows_response(req, channel, args.into_inner(), bytes).await
    }

    // Handle www-form-data request
    #[inline]
    pub async fn form_handler(
        req: HttpRequest,
        channel: web::Data<Channel>,
        bytes: web::Bytes,
    ) -> web::Either<HttpResponse, impl Responder> {
        // NOTE: we cannot have both Bytes and Form at the same time
        // since Form will consume data
        let args = match serde_urlencoded::from_bytes::<Ows>(&bytes) {
            Err(err) => {
                let message = format!("Invalid OWS www-form-data body: {}", err);
                log::error!("{}", message);
                return web::Either::Left(HttpResponse::BadRequest().body(message));
            }
            Ok(args) => args,
        };

        web::Either::Right(ows_response(req, channel, args, bytes).await)
    }
}

//
// QGIS api handlers
//

pub mod api {

    use super::*;

    #[derive(Deserialize)]
    pub struct Map {
        #[serde(alias = "map", alias = "Map", alias = "MAP")]
        map: Option<String>,
    }

    async fn api_response(
        req: HttpRequest,
        channel: web::Data<Channel>,
        path: String,
        args: web::Query<Map>,
        data: web::Bytes,
        endpoint: web::Data<ApiEndPoint>,
    ) -> impl Responder {
        let mut client = channel.client();

        let request_id = request::request_id(&req).map(String::from);
        let content_type =
            request::header_as_str(&req, http::header::CONTENT_TYPE).map(String::from);

        let name = endpoint
            .delegate_to
            .clone()
            .unwrap_or(endpoint.endpoint.clone());

        let mut request = tonic::Request::new(ApiRequest {
            name,
            path,
            target: args.into_inner().map,
            url: Some(request::location(&req)),
            direct: channel.allow_direct_resolution(),
            options: Some(req.query_string().to_string()),
            method: req.method().as_str().to_string(),
            data: (!data.is_empty()).then(|| data.to_vec()),
            delegate: endpoint.delegate_to.is_some(),
            request_id: request_id.clone(),
            content_type,
        });

        request.set_timeout(channel.timeout());

        // forward headers
        metadata::insert_from_headers(request.metadata_mut(), req.headers(), |h| {
            channel.allow_header(h)
        });

        StreamedResponse::new(
            client.execute_api_request(request).await,
            channel.name(),
            request_id,
        )
        .into_response(channel)
    }

    // Handlers
    #[inline]
    pub async fn handler(
        req: HttpRequest,
        channel: web::Data<Channel>,
        path: web::Path<String>,
        map: web::Query<Map>,
        data: web::Bytes,
        endpoint: web::Data<ApiEndPoint>,
    ) -> impl Responder {
        api_response(req, channel, path.into_inner(), map, data, endpoint).await
    }

    #[inline]
    pub async fn default_handler(
        req: HttpRequest,
        channel: web::Data<Channel>,
        map: web::Query<Map>,
        data: web::Bytes,
        endpoint: web::Data<ApiEndPoint>,
    ) -> impl Responder {
        api_response(req, channel, String::default(), map, data, endpoint).await
    }
}
