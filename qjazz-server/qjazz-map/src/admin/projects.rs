//
//  Projects
//

use crate::channel::{
    Channel, QjazzAdminClient,
    qjazz_service::{CheckoutRequest, DropRequest, Empty, ProjectRequest},
};
use crate::responses::{HttpStatusCode, undisclosed_uri, json_collection_stream};
use actix_web::{HttpResponse, HttpResponseBuilder, Responder, Result, error, web};
use futures::stream::StreamExt;

#[derive(serde::Deserialize)]
pub struct Params {
    uri: Option<String>,
}

//
// Get project cache infos
//

// GET

pub async fn get_projects(
    channel: web::Data<Channel>,
    query: web::Query<Params>,
) -> Result<impl Responder> {
    match query.into_inner().uri {
        Some(uri) => checkout_project(channel, uri, false).await,
        None => list_projects(channel.admin_client(), channel).await,
    }
}

#[derive(serde::Deserialize)]
pub struct Details {
    details: Option<bool>,
}

pub async fn get_project_with(
    channel: web::Data<Channel>,
    location: web::Path<String>,
    query: web::Query<Details>,
) -> Result<impl Responder> {
    if query.details.unwrap_or(false) {
        project_infos(channel, location.into_inner()).await
    } else {
        checkout_project(channel, location.into_inner(), false).await
    }
}

// DELETE

pub async fn delete_projects(
    channel: web::Data<Channel>,
    query: web::Query<Params>,
) -> Result<impl Responder> {
    match query.into_inner().uri {
        Some(uri) => drop_project(channel, uri).await,
        None => clear_cache(channel).await,
    }
}

pub async fn delete_project_with(
    channel: web::Data<Channel>,
    location: web::Path<String>,
) -> Result<impl Responder> {
    drop_project(channel, location.into_inner()).await
}

//
// Checkout project and return cache infos
// The operation will pull the project into project's caches
//

// POST

#[derive(Debug, serde::Deserialize)]
pub struct CheckoutParams {
    uri: Option<String>,
}

pub async fn pull_projects(
    channel: web::Data<Channel>,
    params: web::Json<CheckoutParams>,
) -> Result<impl Responder> {
    match params.into_inner().uri {
        Some(uri) => checkout_project(channel, uri, true).await,
        None => update_projects(channel).await,
    }
}

async fn checkout_project(
    channel: web::Data<Channel>,
    uri: String,
    pull: bool,
) -> Result<HttpResponse> {
    if uri.is_empty() {
        //|| !uri.starts_with("/") {
        return Err(error::ErrorBadRequest("Invalid uri"));
    }

    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(CheckoutRequest {
        uri: uri.clone(),
        pull: Some(pull),
    });

    request.set_timeout(channel.timeout());
    match client.checkout_project(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .json({
                // NOTE: Do not leak internal uri
                let mut item = resp.into_inner();
                item.uri = uri;
                item
            })),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}

async fn update_projects(channel: web::Data<Channel>) -> Result<HttpResponse> {
    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(Empty {});

    request.set_timeout(channel.timeout());
    match client.update_cache(request).await {
        Ok(_) => list_projects(client, channel).await,
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}

async fn list_projects(
    mut client: QjazzAdminClient,
    channel: web::Data<Channel>,
) -> Result<HttpResponse> {
    let mut request = tonic::Request::new(Empty {});

    let undisclosed = channel.undisclosed();

    request.set_timeout(channel.timeout());
    match client.list_cache(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .streaming(json_collection_stream(
                resp.into_inner().map(move |mut item| {
                    if undisclosed && let Ok(item) = item.as_mut() {
                        item.uri = undisclosed_uri(&item.uri);
                    }
                    item
                }),
                channel,
            ))),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}

async fn drop_project(channel: web::Data<Channel>, uri: String) -> Result<HttpResponse> {
    if uri.is_empty() {
        return Err(error::ErrorBadRequest("Invalid uri"));
    }

    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(DropRequest { uri: uri.clone() });

    let undisclosed = channel.undisclosed();
    
    request.set_timeout(channel.timeout());
    match client.drop_project(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .json({
                // NOTE: Do not leak internal uri
                let mut item = resp.into_inner();
                if undisclosed {
                    item.uri = uri;
                }
                item
            })),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}

async fn clear_cache(channel: web::Data<Channel>) -> Result<HttpResponse> {
    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(Empty {});

    request.set_timeout(channel.timeout());
    match client.clear_cache(request).await {
        Ok(_) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .body("{}")),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}

async fn project_infos(channel: web::Data<Channel>, uri: String) -> Result<HttpResponse> {
    if uri.is_empty() {
        return Err(error::ErrorBadRequest("Invalid uri"));
    }

    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(ProjectRequest { uri: uri.clone() });

    let undisclosed = channel.undisclosed();
    
    request.set_timeout(channel.timeout());
    match client.get_project_info(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .json({
                // NOTE: Do not leak internal uri
                let mut item = resp.into_inner();
                if undisclosed {
                    item.uri = uri;
                    item.filename = "<undisclosed>".to_string();
                    for layer in item.layers.iter_mut() {
                        layer.source = "<undisclosed>".to_string();
                    }
                }
                item
            })),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(HttpResponseBuilder::new(HttpStatusCode::from(&status).code()).finish())
        }
    }
}
