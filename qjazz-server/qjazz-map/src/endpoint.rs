//!
//! Backend api endpoint
//!
use actix_web::web;
use std::sync::Arc;

use crate::resolver::ApiEndPoint;

/// Wrapper around [`ApiEndpoint`]
#[derive(Clone)]
pub struct EndPoint {
    def: Arc<ApiEndPoint>,
    path: Arc<str>,
}

impl EndPoint {
    pub fn new(def: Arc<ApiEndPoint>, path: String) -> web::ThinData<Self> {
        web::ThinData(Self {
            def,
            path: Arc::from(path),
        })
    }

    #[inline(always)]
    pub fn name(&self) -> &str {
        &self.def.name
    }

    #[inline(always)]
    pub fn endpoint(&self) -> &str {
        &self.def.endpoint
    }

    #[inline(always)]
    pub fn delegate(&self) -> bool {
        self.def.delegate
    }

    #[inline(always)]
    pub fn path(&self) -> &str {
        &self.path
    }
}
