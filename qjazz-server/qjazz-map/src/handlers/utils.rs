// Web utils

use actix_web::{
    HttpRequest,
    http::header::{AsHeaderName, HeaderMap},
    web,
};

pub mod request {

    #[derive(Default, Copy, Clone)]
    pub struct ProxyHeaders {
        pub allow: bool,
    }

    use super::*;

    /// Return a public url from Forwarded header informations
    /// as defined as defined in RFC 7239
    /// see https://docs.rs/actix-web/latest/actix_web/dev/struct.ConnectionInfo.html
    pub fn public_url(req: &HttpRequest, path: &str) -> String {
        if req
            .app_data::<web::ThinData<ProxyHeaders>>()
            .map(|data| data.0.allow)
            .unwrap_or(false)
        {
            let info = req.connection_info();

            let host = info.host();
            let proto = info.scheme();
            let prefix = req
                .headers()
                .get("x-forwarded-prefix")
                .map(|p| p.to_str().unwrap_or_default())
                .unwrap_or_default()
                .trim_end_matches('/');

            let path = path.trim_end_matches('/');

            format!("{proto}://{host}{prefix}{path}")
        } else {
            format!("{}", req.uri())
        }
    }

    #[inline]
    pub fn location(req: &HttpRequest) -> String {
        public_url(req, req.path())
    }

    #[inline]
    pub fn header_as_str(req: &HttpRequest, key: impl AsHeaderName) -> Option<&str> {
        super::header::get_as_str(req.headers(), key)
    }

    #[inline]
    pub fn request_id(req: &HttpRequest) -> Option<&str> {
        super::header::request_id(req.headers())
    }
}

pub mod header {
    use super::*;

    /// Infaillible method that returns header as str
    pub fn get_as_str(headers: &HeaderMap, key: impl AsHeaderName) -> Option<&str> {
        headers.get(key).and_then(|v| v.to_str().ok())
    }

    #[inline]
    pub fn request_id(headers: &HeaderMap) -> Option<&str> {
        get_as_str(headers, "x-request-id")
    }
}
