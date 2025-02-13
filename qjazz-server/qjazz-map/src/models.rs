use serde::Serialize;
use std::borrow::Cow;
use std::ops::Not;

pub mod apis;
pub mod bbox;
pub mod point;

#[derive(Default, Debug, Serialize)]
#[serde(default, rename_all = "camelCase")]
pub struct Link<'a> {
    pub href: Cow<'a, str>,
    pub rel: Cow<'a, str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub r#type: Option<Cow<'a, str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<Cow<'a, str>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<Cow<'a, str>>,
    #[serde(skip_serializing_if = "<&bool>::not")]
    pub templated: bool,
}

impl<'a> Link<'a> {
    pub fn new(href: Cow<'a, str>, rel: &'a str) -> Self {
        Self {
            href,
            rel: rel.into(),
            ..Default::default()
        }
    }
    pub fn application_json(href: Cow<'a, str>, rel: &'a str) -> Self {
        Self {
            href,
            rel: rel.into(),
            r#type: Some(mime::APPLICATION_JSON.as_ref().into()),
            ..Default::default()
        }
    }
    pub fn media_type(mut self, r#type: &'a str) -> Self {
        self.r#type = Some(r#type.into());
        self
    }
    pub fn title(mut self, title: &'a str) -> Self {
        self.title = Some(title.into());
        self
    }
    pub fn description(mut self, description: &'a str) -> Self {
        self.description = Some(description.into());
        self
    }
    pub fn templated(mut self) -> Self {
        self.templated = true;
        self
    }
}

pub mod rel {
    pub const SELF: &str = "self";
    pub const NEXT: &str = "next";
    pub const PREV: &str = "prev";
    pub const ITEM: &str = "item";
    pub const COLLECTION: &str = "collection";
    //pub const RELATED: &str = "related";
    pub const OGC_REL_MAP: &str = "[ogc-rel:map]";
    pub const OGC_REL_ITEM: &str = "[ogc-rel:item]";
    pub const OGC_REL_DATA: &str = "[ogc-rel:data]";
    pub const OGC_REL_LEGEND: &str = "[ogc-rel:legend]";
}
