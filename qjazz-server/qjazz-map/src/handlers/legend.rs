//
// OGC map api/legend
//
// The map/legend api is implemented as a mapping to ows WMS/GetLegendGraphic request
//
use actix_web::{web, HttpRequest, Responder, Result};

use crate::channel::qjazz_service::OwsRequest;
use crate::channel::Channel;
use crate::handlers::response::execute_ows_request;
use crate::handlers::utils::request;

//
//  Default legend handler
//
pub async fn default_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: web::Path<(String, String)>,
) -> Result<impl Responder> {
    let (target, layer) = location.into_inner();
    legend_request(req, channel, target, layer, None).await
}

//
// Styled legend handler
//
pub async fn styled_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: web::Path<(String, String, String)>,
) -> Result<impl Responder> {
    let (target, layer, style) = location.into_inner();
    legend_request(req, channel, target, layer, Some(style)).await
}

pub async fn legend_request(
    req: HttpRequest,
    channel: web::Data<Channel>,
    target: String,
    layer: String,
    style: Option<String>,
) -> Result<impl Responder> {
    let request_id = request::request_id(&req).map(String::from);

    let mut options = format!(
        concat!(
            "service=WMS&request=GetLegendGraphic&version=1.3.0&format=image/png",
            "&layer={}",
        ),
        layer,
    );

    if let Some(style) = style {
        options = format!("{options}&style={style}");
    }

    let request = OwsRequest {
        target,
        service: String::default(), // WMS by default,
        request: "GetLegendGraphic".into(),
        options: Some(options),
        version: None,
        method: None, // 'GET' by default
        url: Some(request::location(&req)),
        direct: channel.allow_direct_resolution(),
        request_id: request_id.clone(),
        body: None,
        content_type: None,
    };

    execute_ows_request(req, channel, request_id, request).await
}
