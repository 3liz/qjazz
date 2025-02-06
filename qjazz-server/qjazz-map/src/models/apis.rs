//
// OGC api supports
// NOTE: keep in sync with qjazz_pool::messages::OgcEndpoints
//

bitflags::bitflags! {
    #[derive(Copy, Clone, Debug)]
    pub struct OgcEndpoints: i64 {
        const MAP = 0x01;
        const FEATURES = 0x02;
        const COVERAGE = 0x04;
        const TILE = 0x08;
        const STYLE = 0x010;
    }
}
