// See https://docs.rs/actix-cors/latest/actix_cors/index.html
use actix_cors::Cors;
use actix_web::{http, http::header};
use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use std::fmt;
use std::str::FromStr;

#[derive(Debug, Clone)]
struct Method(http::Method);

impl Serialize for Method {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.0.as_str().serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for Method {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct Visitor;

        impl de::Visitor<'_> for Visitor {
            type Value = Method;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("Expecting http method verb: GET, ... ")
            }

            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
                Ok(Method(http::Method::from_str(v).map_err(|_| {
                    de::Error::invalid_value(de::Unexpected::Str(v), &self)
                })?))
            }
        }

        deserializer.deserialize_str(Visitor)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
enum Origins {
    #[serde(rename = "any")]
    Any,
    #[serde(rename = "same-origin")]
    SameOrigin,
    #[serde(rename = "hosts")]
    Hosts(Vec<String>),
}

impl Default for Origins {
    fn default() -> Self {
        Self::Any
    }
}

impl Origins {
    fn configure(&self, cors: Cors) -> Cors {
        match self {
            Self::Any => cors.allow_any_origin(),
            // Activated by default
            // See 'method.block_on_origin_mismatch'
            // at https://docs.rs/actix-cors/latest/actix_cors
            Self::SameOrigin => cors,
            Self::Hosts(hosts) => hosts.iter().fold(cors, |cors, o| cors.allowed_origin(o)),
        }
    }
}

/// CORS configuration
#[derive(Default, Debug, Clone, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct CorsConfig {
    allowed_methods: Vec<Method>,
    allowed_headers: Vec<String>,
    allowed_origins: Origins,
    max_age: Option<usize>,
}

impl CorsConfig {
    fn allowed_methods(&self, cors: Cors) -> Cors {
        if self.allowed_methods.is_empty() {
            cors.allow_any_method()
        } else {
            cors.allowed_methods(self.allowed_methods.iter().map(|m| m.0.as_str()))
        }
    }

    fn allowed_headers(&self, cors: Cors) -> Cors {
        if self.allowed_headers.is_empty() {
            cors.allow_any_header()
        } else {
            // Add the CORS safelisted headers
            // See https://developer.mozilla.org/en-US/docs/Glossary/CORS-safelisted_request_header
            cors.allowed_header(header::ACCEPT)
                .allowed_header(header::ACCEPT_LANGUAGE)
                .allowed_header(header::CONTENT_LANGUAGE)
                .allowed_header(header::CONTENT_TYPE)
                .allowed_header(header::RANGE)
                // Required if the request has an "Authorization" header.
                // This is useful to implement authentification on top QGIS SERVER
                // https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Access-Control-Allow-Headers             // https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization
                .allowed_header(header::AUTHORIZATION)
                .allowed_headers(&self.allowed_headers)
        }
    }

    pub fn configure(&self) -> Cors {
        let cors = self.allowed_methods(Cors::default());
        let cors = self.allowed_headers(cors);
        self.allowed_origins
            .configure(cors)
            .max_age(self.max_age)
            .send_wildcard()
    }
}
