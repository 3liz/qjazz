//
// Conformances page
//
//
use actix_web::{HttpRequest, HttpResponse};

use serde::Serialize;

use crate::handlers::utils::request;
use crate::models::{rel, Link};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Conformance<'a> {
    conforms_to: &'static [&'static str],
    links: [Link<'a>; 1],
}

// Ref: https://docs.ogc.org/is/20-058/20-058.html
const MAP_CONFORMANCES: [&str; 12] = [
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/core",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/background",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/collections-selection",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/display-resolution",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/crs",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/map",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/dataset-map",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/styled-map",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/png",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/jpeg",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/api-operations",
    "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/cors",
    // XXX Partial implementation
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/scaling",
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/spatials-subsetting",
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/datetime",
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/general-subsetting",
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/orientation",
    //"https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/projection",
];

pub async fn handler(req: HttpRequest) -> HttpResponse {
    let public_url = request::location(&req);

    HttpResponse::Ok().json(Conformance {
        conforms_to: &MAP_CONFORMANCES,
        links: [Link::application_json((&public_url).into(), rel::SELF)
            .title("OGC API conformance classes")],
    })
}
