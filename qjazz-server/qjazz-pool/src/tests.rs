//!
//! Unit tests
//!
use env_logger;
use std::sync::Once;

static INIT: Once = Once::new();

pub fn setup() {
    // Init setup
    INIT.call_once(|| {
        env_logger::init();
    });
}

#[macro_export]
macro_rules! rootdir {
    ($name:expr) => {
        std::path::Path::new(&std::env::var("CARGO_MANIFEST_DIR").unwrap())
            .join("tests")
            .as_path()
            .join($name)
            .as_path()
            .as_os_str()
            .to_string_lossy()
            .into_owned()
    };
}

//
//  Test messages
//
use crate::Builder;
use crate::messages as msg;
use std::collections::HashMap;

#[tokio::test]
async fn test_messages_io() {
    setup();

    let mut w = Builder::new(crate::rootdir!("process.py"))
        .name("test")
        .start()
        .await
        .unwrap();

    assert_eq!(w.ping("hello").await.unwrap(), "hello");

    let resp = w.get_env().await.unwrap();
    let env = resp.as_object();
    assert!(env.is_some());
    // TODO: Check for specific env variable
    //
    // Ows Request
    //
    let mut resp = w
        .request(msg::OwsRequestMsg {
            service: "WFS",
            request: "GetCapabilities",
            target: "/france/france_parts",
            url: Some("http://localhost:8080/test.3liz.com"),
            version: None,
            direct: false,
            options: None,
            headers: vec![("content-type", "application/test")],
            request_id: None,
            header_prefix: Some("x-test-"),
            content_type: Some("application/test"),
            method: None,
            body: None,
        })
        .await
        .unwrap();

    assert_eq!(resp.status_code, 200);

    let headers = HashMap::<String, String>::from_iter(resp.headers.drain(..));
    assert_eq!(
        headers
            .get("x-test-content-type")
            .expect("Header not found"),
        "application/test"
    );
    assert_eq!(resp.checkout_status, Some(msg::CheckoutStatus::NEW));

    let mut stream = w.byte_stream().unwrap();

    assert_eq!(*(stream.next().await.unwrap().unwrap()), *b"chunk1");
    assert_eq!(*(stream.next().await.unwrap().unwrap()), *b"chunk2");
    assert_eq!(stream.next().await.unwrap(), None);

    //
    // Api Request
    //
    let resp = w
        .request(msg::ApiRequestMsg {
            name: "WFS3",
            path: "/wfs3/collections",
            method: msg::HTTPMethod::GET,
            url: Some("http://localhost:8080/features"),
            data: None,
            delegate: false,
            target: Some("/france/france_parts"),
            direct: false,
            options: None,
            headers: vec![("content-type", "application/test")],
            request_id: None,
            header_prefix: Some("x-test-"),
            content_type: Some("application/test"),
        })
        .await
        .unwrap();

    let mut stream = w.byte_stream().unwrap();

    assert_eq!(resp.status_code, 200);
    assert_eq!(*(stream.next().await.unwrap().unwrap()), *b"<data>");
    assert_eq!(stream.next().await.unwrap(), None);

    // Collections
    let resp = w.collections(None, None, 0..100).await.unwrap();

    assert_eq!(resp.next, false);
    assert_eq!(resp.items.len(), 1);
    assert!(resp.items[0].endpoints.contains(msg::OgcEndpoints::MAP));
    assert!(
        resp.items[0]
            .endpoints
            .contains(msg::OgcEndpoints::FEATURES)
    );
    assert!(
        !resp.items[0]
            .endpoints
            .contains(msg::OgcEndpoints::COVERAGE)
    );

    // CheckoutProjectMsg
    let resp = w.checkout_project("checkout", true).await.unwrap();
    assert_eq!(resp.name.unwrap(), "checkout");

    // UpdateCacheMsg + list_cache
    w.update_cache().await.unwrap();

    let mut resp = w.list_cache().await.unwrap();
    let mut count = 0u32;
    while let Some(info) = resp.next().await.unwrap() {
        assert_eq!(info.cache_id, "test");
        count += 1;
    }
    assert_eq!(count, 1);

    // DropProjectMsg
    let resp = w.drop_project("checkout").await.unwrap();
    assert_eq!(resp.name.unwrap(), "checkout");
    assert_eq!(resp.status, 2);

    // CatalogMsg
    let mut resp = w.catalog(Some("/france")).await.unwrap();
    while let Some(item) = resp.next().await.unwrap() {
        assert!(item.name.starts_with("cat_"));
    }

    // ClearCacheMsg
    w.clear_cache().await.unwrap();

    // GetProjectInfoMsg
    let uri = "/france/france_parts";
    let resp = w.project_info(uri).await.unwrap();
    assert_eq!(resp.uri, uri);
    assert_eq!(resp.layers.len(), 1);
    assert_eq!(resp.layers[0].name, "Layer");

    // Plugins
    let mut resp = w.list_plugins().await.unwrap();
    while let Some(item) = resp.next().await.unwrap() {
        assert!(item.name.starts_with("plugin_"));
    }

    /*
    pub async fn project_info(&mut self, uri: &str) -> Result<msg::ProjectInfo> {
    pub async fn list_plugins(&mut self) -> Result<ObjectStream<msg::PluginInfo>> {
    */
}
