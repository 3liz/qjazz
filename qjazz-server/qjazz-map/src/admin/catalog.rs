//
//  Catalog
//

use crate::channel::{Channel, qjazz_service::CatalogRequest};
use crate::responses::{HttpStatusCode, undisclosed_uri, json_collection_stream};
use actix_web::{HttpResponse, HttpResponseBuilder, Responder, Result, web};
use futures::stream::StreamExt;

#[inline]
pub async fn catalog(channel: web::Data<Channel>) -> Result<impl Responder> {
    catalog_request(channel, None).await
}

#[inline]
pub async fn catalog_with(
    channel: web::Data<Channel>,
    location: web::Path<String>,
) -> Result<impl Responder> {
    catalog_request(channel, Some(location.into_inner())).await
}

async fn catalog_request(
    channel: web::Data<Channel>,
    location: Option<String>,
) -> Result<impl Responder> {
    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(CatalogRequest { location });

    let undisclosed = channel.undisclosed();

    request.set_timeout(channel.timeout());

    match client.catalog(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .streaming(json_collection_stream(
                resp.into_inner().map(move |mut item| {
                    if undisclosed && let Ok(item) = item.as_mut() {
                        item.uri = undisclosed_uri(&item.uri)
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
