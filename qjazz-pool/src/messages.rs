//! Messages
//!
//! Defines messages and reply for worker processes
//! communication
//!
use serde::{Deserialize, Serialize, Serializer};
use std::collections::HashMap;

use crate::errors;

pub type JsonValue = serde_json::Value;

#[allow(non_camel_case_types)]
#[derive(Clone, Copy, Debug)]
pub enum MsgType {
    PING = 1,
    //QUIT = 2,    XXX: Deprecated
    //REQUEST = 3, XXX: Deprecated
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

pub trait RequestMessage: Pickable {}

impl RequestMessage for OwsRequestMsg<'_> {}
impl RequestMessage for ApiRequestMsg<'_> {}

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
    pub headers: HashMap<String, String>,
    pub request_id: Option<&'a str>,
    pub debug_report: bool,
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
    pub headers: HashMap<String, String>,
    pub request_id: Option<&'a str>,
    pub debug_report: bool,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct RequestReply {
    pub status_code: i64,
    pub checkout_status: Option<i64>,
    pub headers: HashMap<String, String>,
    pub cache_id: String,
}

#[derive(Serialize, Deserialize, Debug, PartialEq)]
pub struct RequestReport {
    pub memory: Option<i64>,
    pub timestamp: f64,
    pub duration: f64,
}
//
// CACHE
//

#[allow(non_camel_case_types)]
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum CheckoutStatus {
    UNCHANGED = 0,
    NEEDUPDATE = 1,
    REMOVED = 2,
    NOTFOUND = 3,
    NEW = 4,
    UPDATED = 5,
}

impl Serialize for CheckoutStatus {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_i64(*self as i64)
    }
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
pub struct ListCacheMsg {
    pub status_filter: Option<CheckoutStatus>,
}

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
    pub timestamp: Option<f64>,
    pub name: String,
    pub storage: String,
    pub last_modified: Option<f64>,
    pub saved_version: Option<String>,
    pub debug_metadata: HashMap<String, i64>,
    pub cache_id: String,
    pub last_hit: f64,
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
    pub last_modified: f64,
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
    pub last_modified: f64,
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
    pub logging: &'a str,
    pub config: JsonValue,
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
    use serde_json;

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
            headers: HashMap::new(),
            request_id: Some("1234"),
            debug_report: false,
        };

        // Create buffer
        let mut buf = String::new();
        serde_json::to_writer(unsafe { buf.as_mut_vec() }, &Message::from(msg)).unwrap();
        assert_eq!(
            buf,
            concat!(
                r#"{"msg_id":5,"#,
                r#""name":"Test","#,
                r#""path":"/api/path","#,
                r#""method":"GET","#,
                r#""url":"http://foobar.com","data":[102,111,111,98,97,114],"#,
                r#""delegate":false,"#,
                r#""target":"MyProject","#,
                r#""direct":false,"#,
                r#""options":null,"#,
                r#""headers":{},"#,
                r#""request_id":"1234","debug_report":false}"#,
            ),
        );
    }
}
