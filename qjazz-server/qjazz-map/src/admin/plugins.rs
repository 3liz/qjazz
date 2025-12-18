//
// Plugins
//
use crate::channel::{
    Channel,
    qjazz_service::{Empty, PluginInfo},
};

use crate::responses::{HttpStatusCode, json_collection_stream};
use actix_web::{HttpResponse, HttpResponseBuilder, Responder, Result, web};
use futures::stream::StreamExt;

pub async fn plugins(channel: web::Data<Channel>) -> Result<impl Responder> {
    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(Empty {});

    request.set_timeout(channel.timeout());

    fn from_info(p: PluginInfo) -> serde_json::Value {
        match serde_json::from_str::<serde_json::Value>(&p.metadata) {
            Ok(mut v) => v
                .get_mut("general")
                .map(|v| v.take())
                .unwrap_or_else(|| serde_json::Value::String(format!("{} <no infos>", p.name))),
            Err(err) => {
                log::error!("Failed to get plugin metadata for {}: {err}", p.path);
                serde_json::Value::String(format!("{} <no infos>", p.name))
            }
        }
    }

    match client.list_plugins(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .streaming(json_collection_stream(
                resp.into_inner().map(|item| item.map(from_info)),
                channel,
            ))),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(
                HttpResponseBuilder::new(HttpStatusCode::from(&status).code())
                    .content_type(mime::TEXT_PLAIN)
                    .body(status.message().to_string()),
            )
        }
    }
}
