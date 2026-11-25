//
// Backend metrics
//
use crate::channel::{
    Channel,
    qjazz_service::Empty,
};

use crate::handlers::response;
use actix_web::{HttpResponse, Responder, Result, web};

pub async fn stats(channel: web::Data<Channel>) -> Result<impl Responder> {
    let mut client = channel.admin_client();
    let mut request = tonic::Request::new(Empty {});

    request.set_timeout(channel.timeout());

    match client.stats(request).await {
        Ok(resp) => Ok(HttpResponse::Ok()
            .content_type(mime::APPLICATION_JSON)
            .json(resp.into_inner())),
        Err(status) => {
            log::error!("Backend error:\t{}\t{status}", channel.name());
            Ok(response::from_rpc_status(&status, None))
        }
    }
}
