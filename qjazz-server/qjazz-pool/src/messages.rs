//! Messages
//!
//! Defines messages and reply for worker processes
//! communication
//!
use serde::{Deserialize, Serialize, Serializer, de};
use std::collections::HashMap;

use crate::errors;

pub type JsonValue = serde_json::Value;

#[allow(non_camel_case_types)]
#[derive(Clone, Copy, Debug)]
pub enum MsgType {
    PING = 1,
    OWSREQUEST = 4,
    APIREQUEST = 5,
    CHECKOUT_PROJECT = 6,
    DROP_PROJECT = 7,
    CLEAR_CACHE = 8,
    LIST_CACHE = 9,
    UPDATE_CACHE = 10,
    PROJECT_INFO = 11,
    PLUGINS = 12,
    CATALOG = 13,
    PUT_CONFIG = 14,
    GET_CONFIG = 15,
    ENV = 16,
    STATS = 17,
    SLEEP = 18,
    COLLECTIONS = 19,
}

// Pickable Trait
pub trait Pickable: Serialize {
    fn msg_id() -> MsgType;
}

impl Serialize for MsgType {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_i64(*self as i64)
    }
}

pub struct Message<T: Pickable>(T);

impl<T> From<T> for Message<T>
where
    T: Pickable,
{
    fn from(msg: T) -> Self {
        Self(msg)
    }
}

impl<T: Pickable> Serialize for Message<T> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        #[derive(Serialize)]
        struct XSer<'a, T> {
            msg_id: i64,
            #[serde(flatten)]
            msg: &'a T,
        }

        XSer {
            msg_id: T::msg_id() as i64,
            msg: &self.0,
        }
        .serialize(serializer)
    }
}

// Macro for implementing Pickable
macro_rules! impl_message {
    ($type:ident <'a> , $id:ident) => {
        impl<'a> Pickable for $type<'a> {
            fn msg_id() -> MsgType {
                return MsgType::$id;
            }
        }
    };
    ($type:ident, $id:ident) => {
        impl Pickable for $type {
            fn msg_id() -> MsgType {
                return MsgType::$id;
            }
        }
    };
}

impl_message! {PingMsg<'a>, PING}

/// PING Message
///
/// Send a ping message with an `echo` string
#[derive(Serialize)]
pub struct PingMsg<'a> {
    pub echo: &'a str,
}

//
// REQUEST
//

/// HTTP method for QGIS Request messages
#[derive(Clone, Copy, Debug, Serialize)]
pub enum HTTPMethod {
    GET,
    HEAD,
    POST,
    PUT,
    DELETE,
    CONNECT,
    OPTIONS,
    TRACE,
    PATCH,
}

impl TryFrom<&str> for HTTPMethod {
    type Error = errors::Error;

    fn try_from(s: &str) -> Result<Self, Self::Error> {
        match s {
            "GET" => Ok(HTTPMethod::GET),
            "HEAD" => Ok(HTTPMethod::HEAD),
            "POST" => Ok(HTTPMethod::POST),
            "PUT" => Ok(HTTPMethod::PUT),
            "DELETE" => Ok(HTTPMethod::DELETE),
            "CONNECT" => Ok(HTTPMethod::CONNECT),
            "OPTIONS" => Ok(HTTPMethod::OPTIONS),
            "TRACE" => Ok(HTTPMethod::TRACE),
            "PATCH" => Ok(HTTPMethod::PATCH),
            _ => Err(Self::Error::InvalidHttpMethod(s.to_string())),
        }
    }
}

impl_message! {OwsRequestMsg<'a>, OWSREQUEST}
impl_message! {ApiRequestMsg<'a>, APIREQUEST}
impl_message! {CollectionsMsg<'a>, COLLECTIONS}

pub trait RequestMessage: Pickable {}

impl RequestMessage for OwsRequestMsg<'_> {}
impl RequestMessage for ApiRequestMsg<'_> {}
impl RequestMessage for CollectionsMsg<'_> {}

/// OWS request message
#[derive(Serialize)]
pub struct OwsRequestMsg<'a> {
    pub service: &'a str,
    pub request: &'a str,
    pub target: &'a str,
    pub url: Option<&'a str>,
    pub version: Option<&'a str>,
    pub direct: bool,
    pub options: Option<&'a str>,
    pub headers: Vec<(&'a str, &'a str)>,
    pub request_id: Option<&'a str>,
    pub header_prefix: Option<&'a str>,
    pub content_type: Option<&'a str>,
    pub method: Option<HTTPMethod>,
    #[serde(with = "serde_bytes")]
    pub body: Option<&'a [u8]>,
}

/// API request message
#[derive(Serialize)]
pub struct ApiRequestMsg<'a> {
    pub name: &'a str,
    pub path: &'a str,
    pub method: HTTPMethod,
    pub url: Option<&'a str>,
    #[serde(with = "serde_bytes")]
    pub data: Option<&'a [u8]>,
    pub delegate: bool,
    pub target: Option<&'a str>,
    pub direct: bool,
    pub options: Option<&'a str>,
    pub headers: Vec<(&'a str, &'a str)>,
    pub request_id: Option<&'a str>,
    pub header_prefix: Option<&'a str>,
    pub content_type: Option<&'a str>,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct RequestReply {
    pub status_code: i64,
    pub target: Option<String>,
    pub checkout_status: Option<i64>,
    pub headers: Vec<(String, String)>,
    pub cache_id: String,
}

//
// Collections
//

#[derive(Serialize)]
pub struct CollectionsMsg<'a> {
    pub location: Option<&'a str>,
    pub resource: Option<&'a str>,
    pub start: i64,
    pub end: i64,
}

bitflags::bitflags! {
    //#[derive(Copy, Clone, Debug, Deserialize)]
    #[derive(Copy, Clone, Debug)]
    pub struct OgcEndpoints: i64 {
        const MAP = 0x01;
        const FEATURES = 0x02;
        const COVERAGE = 0x04;
        const TILE = 0x08;
        const STYLE = 0x010;
    }
}

impl<'de> Deserialize<'de> for OgcEndpoints {
    #[inline]
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: de::Deserializer<'de>,
    {
        Ok(Self::from_bits_retain(i64::deserialize(deserializer)?))
    }
}

#[derive(Deserialize, Debug)]
pub struct CollectionsItem {
    pub name: String,
    pub json: String,
    pub endpoints: OgcEndpoints,
}

#[derive(Deserialize, Debug)]
pub struct CollectionsPage {
    pub schema: String,
    pub next: bool,
    pub items: Vec<CollectionsItem>,
}

//
// CACHE
//

#[allow(non_snake_case)]
pub mod CheckoutStatus {
    pub const UNCHANGED: i64 = 0;
    pub const NEEDUPDATE: i64 = 1;
    pub const REMOVED: i64 = 2;
    pub const NOTFOUND: i64 = 3;
    pub const NEW: i64 = 4;
    pub const UPDATED: i64 = 5;
}

impl_message! {CheckoutProjectMsg<'a>, CHECKOUT_PROJECT}
impl_message! {DropProjectMsg<'a>, DROP_PROJECT}
impl_message! {ClearCacheMsg, CLEAR_CACHE}
impl_message! {ListCacheMsg, LIST_CACHE}
impl_message! {UpdateCacheMsg, UPDATE_CACHE}
impl_message! {GetProjectInfoMsg<'a>, PROJECT_INFO}
impl_message! {CatalogMsg<'a>, CATALOG}

/// Pull project message
#[derive(Serialize)]
pub struct CheckoutProjectMsg<'a> {
    pub uri: &'a str,
    pub pull: bool,
}

/// Drop project message
#[derive(Serialize)]
pub struct DropProjectMsg<'a> {
    pub uri: &'a str,
}

/// Clear cache message
#[derive(Serialize)]
pub struct ClearCacheMsg;

/// List cache message
#[derive(Serialize)]
pub struct ListCacheMsg;

/// Update cache message
#[derive(Serialize)]
pub struct UpdateCacheMsg;

/// Project info message
#[derive(Serialize)]
pub struct GetProjectInfoMsg<'a> {
    pub uri: &'a str,
}

/// Catalog message
#[derive(Serialize)]
pub struct CatalogMsg<'a> {
    pub location: Option<&'a str>,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct CacheInfo {
    pub uri: String,
    pub status: i64,
    pub in_cache: bool,
    pub timestamp: Option<i64>,
    pub name: Option<String>,
    pub storage: Option<String>,
    pub last_modified: Option<String>,
    pub saved_version: Option<String>,
    pub debug_metadata: HashMap<String, i64>,
    pub cache_id: String,
    pub last_hit: i64,
    pub hits: i64,
    pub pinned: bool,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct LayerInfo {
    pub layer_id: String,
    pub name: String,
    pub source: String,
    pub crs: String,
    pub is_valid: bool,
    pub is_spatial: bool,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct ProjectInfo {
    pub status: i64,
    pub uri: String,
    pub filename: String,
    pub crs: String,
    pub last_modified: String,
    pub storage: String,
    pub has_bad_layers: bool,
    pub layers: Vec<LayerInfo>,
    pub cache_id: String,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct CatalogItem {
    pub uri: String,
    pub name: String,
    pub storage: String,
    pub last_modified: String,
    pub public_uri: String,
}

//
// PLUGINS
//

impl_message! {PluginsMsg, PLUGINS}

#[derive(Serialize)]
pub struct PluginsMsg;

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct PluginInfo {
    pub name: String,
    pub path: String,
    pub plugin_type: String,
    pub metadata: JsonValue,
}

//
// CONFIG
//

impl_message! {GetConfigMsg, GET_CONFIG}
impl_message! {PutConfigMsg<'a>, PUT_CONFIG}

/// Get config message
#[derive(Serialize)]
pub struct GetConfigMsg {}

/// Put config message
#[derive(Serialize)]
pub struct PutConfigMsg<'a> {
    pub config: &'a JsonValue,
}

//
// ENV
//

impl_message! {GetEnvMsg, ENV}

#[derive(Serialize)]
pub struct GetEnvMsg;

//
// SLEEP
//

impl_message! {SleepMsg, SLEEP}

#[derive(Serialize)]
pub struct SleepMsg {
    pub delay: i64,
}

/// An Envelop is a wrapper for response
///
/// The Python process return envelop as a tuple (status, msg)
/// In case of failure (i.e status > 299) any json compatible
/// value may be returned
#[derive(Debug, PartialEq)]
pub enum Envelop<T> {
    Success(i64, T),
    Failure(i64, JsonValue),
    NoData,
    ByteChunk,
}

// =======================
// Tests
// =======================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_serialize_msg() {
        let msg = ApiRequestMsg {
            name: "Test",
            path: "/api/path",
            url: Some("http://foobar.com"),
            method: HTTPMethod::GET,
            data: Some(b"foobar"),
            delegate: false,
            target: Some("MyProject"),
            direct: false,
            options: None,
            headers: vec![("content-type", "application/test")],
            request_id: Some("1234"),
            header_prefix: Some("x-test-"),
            content_type: Some("application/test"),
        };

        let mut buf = Vec::new();
        rmp_serde::encode::write(&mut buf, &Message::from(msg)).unwrap();
    }
}
