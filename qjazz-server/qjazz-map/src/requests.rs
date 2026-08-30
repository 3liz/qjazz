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
            // Build from the raw uri
            let uri = req.uri();
            if let (Some(scheme), Some(authority)) = (uri.scheme_str(), uri.authority()) {
                format!("{}://{}{path}", scheme, authority.as_str())
            } else {
                // No scheme/authority, send as relative uri
                path.into()
            }
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

#[cfg(test)]
mod tests {
    use super::request::*;
    use actix_web::{test::TestRequest, web};

    //
    // Proxy headers allowed: the public url is built from the
    // connection info and the 'x-forwarded-prefix' header.
    //

    #[test]
    fn test_public_url_from_forwarded_headers() {
        let req = TestRequest::default()
            .app_data(web::ThinData(ProxyHeaders { allow: true }))
            .insert_header(("forwarded", "proto=https;host=proxy.example.com"))
            .to_http_request();

        assert_eq!(
            public_url(&req, "/collections"),
            "https://proxy.example.com/collections"
        );
    }

    #[test]
    fn test_public_url_from_forwarded_prefix() {
        let req = TestRequest::default()
            .app_data(web::ThinData(ProxyHeaders { allow: true }))
            .insert_header(("forwarded", "proto=https;host=proxy.example.com"))
            .insert_header(("x-forwarded-prefix", "/qjazz/"))
            .to_http_request();

        // Trailing slashes are trimmed from both the prefix and the path
        assert_eq!(
            public_url(&req, "/collections/"),
            "https://proxy.example.com/qjazz/collections"
        );
    }

    //
    // Proxy headers not allowed: the public url is built from the raw uri.
    //

    #[test]
    fn test_public_url_from_absolute_uri() {
        let req = TestRequest::default()
            .uri("http://localhost:8080/collections")
            .insert_header(("forwarded", "proto=https;host=proxy.example.com"))
            .to_http_request();

        // Forwarded headers are ignored
        assert_eq!(public_url(&req, "/foo"), "http://localhost:8080/foo");
    }

    #[test]
    fn test_public_url_from_absolute_uri_no_proxy_data() {
        // No ProxyHeaders app data at all
        let req = TestRequest::default()
            .uri("https://map.example.com/foo")
            .to_http_request();

        assert_eq!(public_url(&req, "/bar"), "https://map.example.com/bar");
    }

    //
    // Proxy headers not allowed and no scheme/authority in the raw uri:
    // fallback to a relative url.
    //

    #[test]
    fn test_public_url_relative() {
        let req = TestRequest::default()
            .app_data(web::ThinData(ProxyHeaders { allow: false }))
            .uri("/collections")
            .to_http_request();

        assert_eq!(public_url(&req, "/collections"), "/collections");
    }

    #[test]
    fn test_public_url_relative_empty_path() {
        let req = TestRequest::default().uri("/collections").to_http_request();

        assert_eq!(public_url(&req, ""), "");
    }
}
