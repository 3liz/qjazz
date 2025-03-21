use serde::{Deserialize, Deserializer, de};
use std::fmt;
//
// Parsing point from request arguments
//
use std::str::FromStr;

use crate::models::bbox::ParseBboxError;

#[derive(Debug, PartialEq)]
pub enum Point {
    Point2D(f64, f64),
    Point3D(f64, f64, f64),
}

impl FromStr for Point {
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

        let point = if let Some(v3) = i.next() {
            Point::Point3D(v1, v2, parse(Some(v3))?)
        } else {
            Point::Point2D(v1, v2)
        };

        if i.next().is_some() {
            Err(ParseBboxError::too_many_values())
        } else {
            Ok(point)
        }
    }
}

impl<'de> Deserialize<'de> for Point {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct Visitor;

        impl de::Visitor<'_> for Visitor {
            type Value = Point;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("Expecting 2 or 3 comma separated numbers")
            }

            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
                Point::from_str(v)
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
    fn test_point_parse2d() {
        let point = Point::from_str("1,2.0").unwrap();
        assert_eq!(point, Point::Point2D(1.0, 2.0));
    }

    #[test]
    fn test_point_parse3d() {
        let point = Point::from_str("1,2,3.0").unwrap();
        assert_eq!(point, Point::Point3D(1.0, 2.0, 3.0));
    }

    #[test]
    fn test_bbox_deserializer() {
        let point: Point =
            serde_json::from_str(r#""1,2.0""#).expect("Failed to deserialize from string");
        assert_eq!(point, Point::Point2D(1.0, 2.0));
    }
}
