//
// Parsing bounding box from request arguments
//
use serde::{de, Deserialize, Deserializer};
use std::str::FromStr;
use std::{error, fmt};

pub const CRS84: &str = "http://www.opengis.net/def/crs/OGC/1.3/CRS84";

#[derive(Debug, PartialEq)]
pub enum Bbox {
    Box2D([f64; 4]),
    Box3D([f64; 6]),
}

impl fmt::Display for Bbox {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> Result<(), fmt::Error> {
        match self {
            Self::Box2D(a) => write!(f, "{},{},{},{}", a[0], a[1], a[2], a[3]),
            Self::Box3D(a) => write!(f, "{},{},{},{},{},{}", a[0], a[1], a[2], a[3], a[4], a[5],),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ParseBboxError {
    kind: BboxErrorKind,
}

#[derive(Debug, Clone)]
enum BboxErrorKind {
    Invalid,
    Empty,
    ValueMissing,
    TooManyValues,
}

impl ParseBboxError {
    #[inline]
    pub fn invalid() -> Self {
        Self {
            kind: BboxErrorKind::Invalid,
        }
    }
    #[inline]
    pub fn empty() -> Self {
        Self {
            kind: BboxErrorKind::Empty,
        }
    }
    #[inline]
    pub fn value_missing() -> Self {
        Self {
            kind: BboxErrorKind::ValueMissing,
        }
    }
    #[inline]
    pub fn too_many_values() -> Self {
        Self {
            kind: BboxErrorKind::TooManyValues,
        }
    }
}

impl error::Error for ParseBboxError {}

impl fmt::Display for ParseBboxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self.kind {
            BboxErrorKind::Invalid => "Invalid number literal",
            BboxErrorKind::Empty => "Cannot parse from empty string",
            BboxErrorKind::ValueMissing => "Missing values",
            BboxErrorKind::TooManyValues => "Too many  values for bounding box",
        }
        .fmt(f)
    }
}

impl FromStr for Bbox {
    type Err = ParseBboxError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.trim();

        if s.is_empty() {
            return Err(ParseBboxError::empty());
        }

        let mut i = s.split(',');

        fn parse(v: Option<&str>) -> Result<f64, ParseBboxError> {
            v.ok_or(ParseBboxError::value_missing())
                .and_then(|v| f64::from_str(v.trim()).map_err(|_| ParseBboxError::invalid()))
        }

        let v1 = parse(i.next())?;
        let v2 = parse(i.next())?;
        let v3 = parse(i.next())?;
        let v4 = parse(i.next())?;

        let bbox = if let Some(v) = i.next() {
            Bbox::Box3D([v1, v2, v3, v4, parse(Some(v))?, parse(i.next())?])
        } else {
            Bbox::Box2D([v1, v2, v3, v4])
        };

        if i.next().is_some() {
            Err(ParseBboxError::too_many_values())
        } else {
            Ok(bbox)
        }
    }
}

impl<'de> Deserialize<'de> for Bbox {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct Visitor;

        impl de::Visitor<'_> for Visitor {
            type Value = Bbox;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("Expecting 4 or 6 comma separated numbers or sequence")
            }

            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
                Bbox::from_str(v)
                    .map_err(|_| de::Error::invalid_value(de::Unexpected::Str(v), &self))
            }
        }

        deserializer.deserialize_str(Visitor)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bbox_parse2d() {
        let bbox = Bbox::from_str("1,2,3.0, 4.0").unwrap();
        assert_eq!(bbox, Bbox::Box2D([1.0, 2.0, 3.0, 4.0]));
    }

    #[test]
    fn test_bbox_parse3d() {
        let bbox = Bbox::from_str("1,2,3.0, 4.0, 5,6.0").unwrap();
        assert_eq!(bbox, Bbox::Box3D([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]));
    }

    #[test]
    fn test_bbox_deserializer() {
        let bbox: Bbox =
            serde_json::from_str(r#""1,2.0,3.0,4.0""#).expect("Failed to deserialize from string");
        assert_eq!(bbox, Bbox::Box2D([1.0, 2.0, 3.0, 4.0]));
    }
}
