//
// OGC map api
//
// The map api is implemented as a mapping to ows WMS/GetMap request
//
use actix_web::http::header::{self, Header};
use actix_web::{HttpRequest, Responder, Result, error, web};
use serde::Deserialize;
use std::fmt::{self, Write};

use crate::channel::Channel;
use crate::channel::qjazz_service::OwsRequest;
use crate::handlers::response::execute_ows_request;
use crate::requests::request;

use crate::models::bbox::{Bbox, CRS84};
//use crate::models::point::Point;

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
    /*
    #[serde(alias = "void-transparent")]
    void_transparent: Option<bool>,
    #[serde(alias = "void-bgcolor")]
    void_bgcolor: Option<String>,
    */
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

    // Not in OGC specs but allow styling with 'collections' parameter
    // see https://docs.qgis.org/latest/en/docs/server_manual/services/wms.html#wms-styles
    styles: Option<String>,
    format: Option<String>,
}

//
// Map handler
//
pub async fn default_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    location: web::Path<String>,
    params: web::Query<Params>,
) -> Result<impl Responder> {
    map_request(req, channel, location.into_inner(), params).await
}

//
// Collection item (layer) handler
//
pub async fn child_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resources: web::Path<(String, String)>,
    mut params: web::Query<Params>,
) -> Result<impl Responder> {
    let (location, resource) = resources.into_inner();
    params.collections = Some(resource);
    map_request(req, channel, location, params).await
}

//
// Styled map
//
pub async fn styled_child_handler(
    req: HttpRequest,
    channel: web::Data<Channel>,
    resources: web::Path<(String, String, String)>,
    mut params: web::Query<Params>,
) -> Result<impl Responder> {
    let (location, resource, style) = resources.into_inner();
    params.collections = Some(resource);
    params.styles = Some(style);
    map_request(req, channel, location, params).await
}

pub async fn map_request(
    req: HttpRequest,
    channel: web::Data<Channel>,
    target: String,
    params: web::Query<Params>,
) -> Result<impl Responder> {
    let request_id = request::request_id(&req).map(String::from);
    let options = WmsBuilder::build(&params, &req)?.options();

    let request = OwsRequest {
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
    };

    Ok(execute_ows_request(req, &channel, request_id, request)
        .await
        .into_oapi_error_response(channel)
        .await)
}

// WMS options builder
struct WmsBuilder {
    opts: String,
}

impl WmsBuilder {
    // Build wms options out of
    // parameters

    fn write_error(err: fmt::Error) -> error::Error {
        log::error!("Format error: {err}");
        error::ErrorInternalServerError("Internal error")
    }

    fn build(params: &Params, req: &HttpRequest) -> Result<Self> {
        Self {
            opts: "service=WMS&request=GetMap&version=1.3.0".to_string(),
        }
        .scaling(params)?
        .subsetting(params)?
        .display(params)?
        .layers(params)?
        .bgcolor(params)?
        .styles(params)?
        .transparent(params)?
        .format(params, req)
    }

    fn options(self) -> String {
        self.opts
    }

    fn layers(mut self, param: &Params) -> Result<Self> {
        if let Some(collections) = &param.collections {
            write!(self.opts, "&layers={}", percent_encode(collections))
                .map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn scaling(mut self, params: &Params) -> Result<Self> {
        if let Some(width) = &params.width {
            write!(self.opts, "&width={width}").map_err(Self::write_error)?;
        }
        if let Some(height) = &params.height {
            write!(self.opts, "&height={height}").map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn subsetting(mut self, params: &Params) -> Result<Self> {
        if let Some(bbox) = &params.bbox {
            write!(self.opts, "&bbox={bbox}").map_err(Self::write_error)?;
            // In no crs is specified then we SHALL assume that bbox is
            // expressed in CRS84
            let crs = params.bbox_crs.as_deref().unwrap_or(CRS84);
            write!(self.opts, "&crs={}", percent_encode(crs)).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn styles(mut self, params: &Params) -> Result<Self> {
        if let Some(styles) = &params.styles {
            write!(self.opts, "&styles={}", percent_encode(styles)).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn display(mut self, params: &Params) -> Result<Self> {
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
            write!(self.opts, "&bgcolor={}", percent_encode(color)).map_err(Self::write_error)?;
        }
        Ok(self)
    }

    fn transparent(mut self, params: &Params) -> Result<Self> {
        write!(self.opts, "&transparent={}", params.transparent).map_err(Self::write_error)?;
        Ok(self)
    }

    fn format(mut self, params: &Params, req: &HttpRequest) -> Result<Self> {
        // Check format from params then fromacceptance header
        if let Some(format) = params.format.as_deref().or_else(|| {
            header::Accept::parse(req).ok().and_then(|accept| {
                accept
                    .0
                    .into_iter()
                    .map(|q| q.item)
                    .find_map(|m| match (m.type_(), m.subtype()) {
                        (mime::IMAGE, mime::JPEG) => Some("image/jpeg"),
                        (mime::IMAGE, n) if n.as_str() == "webp" => Some("image/webp"),
                        (mime::APPLICATION, n) if n.as_str() == "dxf" => Some("application/dxf"),
                        _ => None,
                    })
            })
        }) {
            write!(self.opts, "&format={}", percent_encode(format)).map_err(Self::write_error)?;
        }
        Ok(self)
    }
}

// Protect against query parameter injection through string parameters
const PARAM_ENCODING_SET: &percent_encoding::AsciiSet = &percent_encoding::CONTROLS
    .add(b' ')
    .add(b'&')
    .add(b'=')
    .add(b'?')
    .add(b'"')
    .add(b'`')
    .add(b'>')
    .add(b'<');

#[inline(always)]
fn percent_encode<'a>(input: &'a str) -> percent_encoding::PercentEncode<'a> {
    percent_encoding::percent_encode(input.as_bytes(), PARAM_ENCODING_SET)
}

#[cfg(test)]
mod tests {
    use super::*;
    use actix_web::http::StatusCode;
    use actix_web::test::TestRequest;

    const BASE: &str = "service=WMS&request=GetMap&version=1.3.0";
    const CRS84_URL: &str = "http://www.opengis.net/def/crs/OGC/1.3/CRS84";

    fn params(query: &str) -> web::Query<Params> {
        web::Query::<Params>::from_query(query)
            .unwrap_or_else(|err| panic!("Failed to parse {query:?}: {err}"))
    }

    // Build options from a query string with no request headers
    fn options(query: &str) -> String {
        options_with(query, TestRequest::default())
    }

    // Build options from a query string and a request builder
    fn options_with(query: &str, req: TestRequest) -> String {
        WmsBuilder::build(&params(query), &req.to_http_request())
            .expect("Expecting valid options")
            .options()
    }

    fn build_error(query: &str) -> error::Error {
        WmsBuilder::build(&params(query), &TestRequest::default().to_http_request())
            .err()
            .expect("Expecting build error")
    }

    #[test]
    fn test_wms_defaults() {
        // Empty parameters: only the constant part, the default display
        // resolution and the default transparency are written.
        assert_eq!(options(""), format!("{BASE}&dpi=90.7&transparent=true"),);
    }

    #[test]
    fn test_wms_options_order() {
        // All the options at once: check the layout of the option string
        let opts = options_with(
            "width=400&height=300&bbox=1,2,3,4&bbox-crs=EPSG:4326\
             &mm-per-pixel=0.14&collections=layer1&bgcolor=0x112233\
             &styles=style1&transparent=false&format=image/png",
            TestRequest::default(),
        );
        assert_eq!(
            opts,
            format!(
                "{BASE}&width=400&height=300&bbox=1,2,3,4&crs=EPSG:4326\
                 &dpi=181.4&layers=layer1&bgcolor=0x112233\
                 &styles=style1&transparent=false&format=image/png"
            ),
        );
    }

    //
    // Scaling (conformance class A.5)
    //

    #[test]
    fn test_wms_scaling() {
        assert!(options("width=800&height=600").contains("&width=800&height=600"));
    }

    #[test]
    fn test_wms_scaling_partial() {
        // Width and height are independent options
        let opts = options("height=600");
        assert!(opts.contains("&height=600"));
        assert!(!opts.contains("&width="));
    }

    //
    // Display resolution (conformance class A.6)
    //

    #[test]
    fn test_wms_display_resolution() {
        // mm-per-pixel is converted to dpi for the QGIS WMS backend
        assert!(options("mm-per-pixel=0.28").contains("&dpi=90.7"));
        assert!(options("mm-per-pixel=0.14").contains("&dpi=181.4"));
        // The snake_case spelling is accepted as well
        assert!(options("mm_per_pixel=0.14").contains("&dpi=181.4"));
    }

    #[test]
    fn test_wms_display_resolution_invalid() {
        // A null or negative resolution is rejected
        for query in ["mm-per-pixel=0", "mm-per-pixel=-1.0"] {
            assert_eq!(
                build_error(query).as_response_error().status_code(),
                StatusCode::BAD_REQUEST,
                "Expecting bad request for {query:?}",
            );
        }
    }

    //
    // Spatial subsetting (conformance class A.7)
    //

    #[test]
    fn test_wms_subsetting_default_crs() {
        // With no bbox-crs, the bbox is assumed to be expressed in CRS84
        assert!(
            options("bbox=1.0,2.0,3.0,4.0").contains(&format!("&bbox=1,2,3,4&crs={CRS84_URL}"))
        );
    }

    #[test]
    fn test_wms_subsetting_explicit_crs() {
        // CURIE form is allowed for WMS compatibility
        assert!(options("bbox=1,2,3,4&bbox-crs=EPSG:3857").contains("&bbox=1,2,3,4&crs=EPSG:3857"));
        assert!(options("bbox=1,2,3,4&bbox_crs=EPSG:3857").contains("&bbox=1,2,3,4&crs=EPSG:3857"));
    }

    #[test]
    fn test_wms_subsetting_3d_bbox() {
        assert!(options("bbox=1,2,3,4,5,6").contains("&bbox=1,2,3,4,5,6&crs="));
    }

    #[test]
    fn test_wms_subsetting_no_crs_without_bbox() {
        // A crs is written only along with a bbox
        assert!(!options("bbox-crs=EPSG:3857").contains("&crs="));
    }

    //
    // Collections selection (conformance class A.4)
    //

    #[test]
    fn test_wms_layers() {
        assert!(options("collections=layer1").contains("&layers=layer1"));
    }

    #[test]
    fn test_wms_layers_encoded() {
        // The collection separator and any special character are escaped
        assert!(options("collections=layer 1,layer/2").contains("&layers=layer%201,layer/2"));
    }

    //
    // Styles
    //

    #[test]
    fn test_wms_styles() {
        assert!(options("styles=style1").contains("&styles=style1"));
        assert!(options("styles=my style,other").contains("&styles=my%20style,other"));
    }

    //
    // Background (conformance class A.3)
    //

    #[test]
    fn test_wms_bgcolor() {
        assert!(options("bgcolor=0x112233").contains("&bgcolor=0x112233"));
        // Values are not validated but they are escaped
        assert!(options("bgcolor=#112233").contains("&bgcolor=#112233"));
    }

    #[test]
    fn test_wms_transparent() {
        assert!(options("transparent=false").contains("&transparent=false"));
        assert!(options("transparent=true").contains("&transparent=true"));
    }

    //
    // Format negotiation
    //

    #[test]
    fn test_wms_format_from_params() {
        assert!(options("format=image/jpeg").contains("&format=image/jpeg"));
    }

    #[test]
    fn test_wms_format_from_accept_header() {
        for (accept, expected) in [
            ("image/jpeg", "&format=image/jpeg"),
            ("image/webp", "&format=image/webp"),
            ("application/dxf", "&format=application/dxf"),
        ] {
            let opts = options_with(
                "",
                TestRequest::default().insert_header((header::ACCEPT, accept)),
            );
            assert!(
                opts.contains(expected),
                "Expecting {expected:?} for accept header {accept:?}, got {opts:?}",
            );
        }
    }

    #[test]
    fn test_wms_format_accept_header_precedence() {
        // The first supported media type of the header is selected
        let opts = options_with(
            "",
            TestRequest::default()
                .insert_header((header::ACCEPT, "text/html, image/webp, image/jpeg")),
        );
        assert!(opts.contains("&format=image/webp"));
    }

    #[test]
    fn test_wms_format_params_override_accept_header() {
        let opts = options_with(
            "format=application/pdf",
            TestRequest::default().insert_header((header::ACCEPT, "image/jpeg")),
        );
        assert!(opts.contains("&format=application/pdf"));
        assert!(!opts.contains("image/jpeg"));
    }

    #[test]
    fn test_wms_format_unsupported_accept_header() {
        // Unhandled media types are left to the backend default
        for accept in ["image/png", "*/*", "text/html"] {
            let opts = options_with(
                "",
                TestRequest::default().insert_header((header::ACCEPT, accept)),
            );
            assert!(
                !opts.contains("&format="),
                "Expecting no format for accept header {accept:?}, got {opts:?}",
            );
        }
    }

    #[test]
    fn test_wms_format_invalid_accept_header() {
        // An unparsable header must not fail the request
        let opts = options_with(
            "",
            TestRequest::default().insert_header((header::ACCEPT, "not a media type")),
        );
        assert!(!opts.contains("&format="));
    }
}
