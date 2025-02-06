//
// OGC map api
//
// The map api is implemented as a mapping to ows WMS/GetMap request
//
use actix_web::{error, web, HttpRequest, Responder, Result};
use serde::Deserialize;
use std::fmt::{self, Write};

use crate::channel::qjazz_service::OwsRequest;
use crate::channel::Channel;
use crate::handlers::response::{
    collect_payload, metadata, service_exception_msg, StreamedResponse,
};
use crate::handlers::utils::request;

use crate::models::bbox::{Bbox, CRS84};
use crate::models::point::Point;

// Serde initilizer
fn true_value() -> bool {
    true
}

#[derive(Debug, Deserialize)]
pub struct Params {
    // Background
    // Conformance class A.3: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/background
    bgcolor: Option<String>,
    #[serde(default = "true_value")]
    transparent: bool,
    // This has no effects with WMS
    #[serde(alias = "void-transparent")]
    void_transparent: Option<bool>,
    #[serde(alias = "void-bgcolor")]
    void_bgcolor: Option<String>,

    // Conformance class A.4:
    // https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/collections-selection
    // A comma separated list of collections id
    collections: Option<String>,

    // Scaling requirements
    // Conformance class A.5: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/scaling
    width: Option<u16>,
    height: Option<u16>,
    //#[serde(alias = "scale-denominator")]
    //scale_denominator: Option<f64>,

    // Display resolution
    // Conformance class A.6: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/display-resolution
    #[serde(alias = "mm-per-pixel")]
    mm_per_pixel: Option<f64>,

    // Spatial subsetting
    // Conformance class A.7: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/spatial-subsetting

    // Only partial conformance

    // Note: using CURIE (compact crs form - i.e 'Authority:Code' - may be allowed
    // for WMS compatibility
    // see CURIE permission in https://docs.ogc.org/is/20-058/20-058.html
    #[serde(alias = "bbox-crs")]
    bbox_crs: Option<String>,
    bbox: Option<Bbox>,
    // NOTE: Noop for WMS
    //#[serde(alias = "subset-crs")]
    //subset_crs: Option<String>,
    //subset: Option<String>,

    //#[serde(alias = "center-crs")]
    //center_crs: Option<String>,
    //center: Option<Point>,

    // Date and Time
    // Conformance class A.8: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/datetime
    // XXX: Not implemented

    // General subsetting
    // Conformance class A.9: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/general-subsetting
    // XXX: Not implemented

    // Coordinate Reference System (output)
    // Conformance class A.10: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/crs
    // XXX: Not implemented: no WMS support
    //crs: Option<String>,

    // Orientation
    //Conformance class A.11: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/orientation
    // XXX: Not implemented

    // Custom Projection CRS
    // Conformance class A.12: https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/projection
    // XXX: Not implemented
}

//
// Map handler
//
pub async fn handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: web::Path<String>,
    params: web::Query<Params>,
) -> Result<impl Responder> {
    map_request(req, channel, location.into_inner(), params).await
}

pub async fn collection_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resources: web::Path<(String, String)>,
    mut params: web::Query<Params>,
) -> Result<impl Responder> {
    let (location, resource) = resources.into_inner();
    params.collections = Some(resource);
    map_request(req, channel, location, params).await
}

pub async fn map_request(
    req: HttpRequest,
    channel: web::Data<Channel>,
    target: String,
    params: web::Query<Params>,
) -> Result<impl Responder> {
    let mut client = channel.client();
    let request_id = request::request_id(&req).map(String::from);

    let options = WmsBuilder::build(&params)?.options();

    let mut request = tonic::Request::new(OwsRequest {
        target,
        options: Some(options),
        service: String::default(),
        request: String::from("qjazz-request-map"),
        version: None,
        method: None,
        url: Some(request::location(&req)),
        direct: channel.allow_direct_resolution(),
        request_id: request_id.clone(),
        body: None,
        content_type: None,
    });

    request.set_timeout(channel.timeout());

    // forward headers
    metadata::insert_from_headers(request.metadata_mut(), req.headers(), |h| {
        channel.allow_header(h)
    });

    match StreamedResponse::new(
        client.execute_ows_request(request).await,
        channel.name(),
        request_id,
    ) {
        StreamedResponse::Fail(resp) => Ok(resp),
        StreamedResponse::Succ(mut builder, resp) => {
            // Check return code
            // XXX: Need to check the returned content type ?
            if builder.status_code().is_success() {
                Ok(builder.stream_bytes(resp, channel.clone()))
            } else {
                let data = collect_payload(resp).await;
                let text = data
                    .as_deref()
                    .map(|b| std::str::from_utf8(b).unwrap_or("<binary data>"));
                log::error!(
                    "{}: Map request returned error: {:?}\n{:?}",
                    channel.name(),
                    builder.status_code(),
                    text,
                );
                Ok(builder.content_type(mime::TEXT_PLAIN).body(
                    match text {
                        Ok(msg) => service_exception_msg(msg),
                        Err(_) => None,
                    }
                    .unwrap_or("Map request error")
                    .to_string(),
                ))
            }
        }
    }
}

// WMS options builder
struct WmsBuilder {
    opts: String,
}

impl WmsBuilder {
    // Build wms options out of
    // parameters

    fn write_error(err: fmt::Error) -> error::Error {
        log::error!("Format error: {}", err);
        error::ErrorInternalServerError("Internal error")
    }

    fn build(params: &Params) -> Result<Self> {
        Self {
            opts: "service=WMS&request=GetMap&version=1.3.0".to_string(),
        }
        .subsetting(params)?
        .display(params)?
        .layers(params)?
        .bgcolor(params)?
        .transparent(params)
    }

    fn options(self) -> String {
        self.opts
    }

    fn layers(mut self, param: &Params) -> Result<Self> {
        if let Some(collections) = &param.collections {
            write!(self.opts, "&layers={}", collections).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn subsetting(mut self, params: &Params) -> Result<Self> {
        if let Some(bbox) = &params.bbox {
            write!(self.opts, "&bbox={}", bbox).map_err(Self::write_error)?;
            // In no crs is specified then we SHALL assume that bbox is
            // expressed in CRS84
            let crs = params.bbox_crs.as_deref().unwrap_or(CRS84);
            write!(self.opts, "&crs={}", crs).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn display(mut self, params: &Params) -> Result<Self> {
        if let Some(mm_per_pixel) = &params.mm_per_pixel {}
        let mm_per_pixel = params.mm_per_pixel.unwrap_or(0.28);
        if mm_per_pixel <= 0. {
            return Err(error::ErrorBadRequest("Invalid mm-per-pixel parameter"));
        }
        // Transform this as dpi for QGIS WMS backend
        write!(self.opts, "&dpi={:.1}", 25.4f64 / mm_per_pixel).map_err(Self::write_error)?;
        Ok(self)
    }

    fn bgcolor(mut self, params: &Params) -> Result<Self> {
        // No validation
        if let Some(color) = &params.bgcolor {
            write!(self.opts, "&bgcolor={}", color).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn transparent(mut self, params: &Params) -> Result<Self> {
        write!(self.opts, "&transparent={}", params.transparent).map_err(Self::write_error)?;
        Ok(self)
    }
}
