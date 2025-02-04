use serde::Serialize;
use std::borrow::Cow;
use std::ops::Not;

#[derive(Default, Debug, Serialize)]
#[serde(default, rename_all = "camelCase")]
pub struct Link<'a> {
    pub href: Cow<'a, str>,
    pub rel: Cow<'a, str>,
    pub r#type: Cow<'a, str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<Cow<'a, str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<Cow<'a, str>>,
    #[serde(skip_serializing_if = "<&bool>::not")]
    pub templated: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hreflang: Option<Cow<'a, str>>,
}

pub mod rel {
    pub const SELF: &str = "self";
    pub const RELATED: &str = "related";
    pub const CHILD: &str = "child";
    pub const COLLECTION: &str = "collection";
}
