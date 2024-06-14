#
# Copyright 2018-2021 3liz
# Author: David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Original parts are Copyright 2016 OSGeo Foundation,
# represented by PyWPS Project Steering Committee,
# and released under MIT license.
# Please consult PYWPS_LICENCE.txt for details
#
from types import MappingProxyType

from pydantic import (
    AnyUrl,
    HttpUrl,
)
from typing_extensions import (
    Optional,
)

OGC_OPENGIS_URL = AnyUrl("https://www.opengis.net")

OGCAPI_PROCESSES_CONFORMANCE_URI = AnyUrl(f'{OGC_OPENGIS_URL}/spec/ogcapi-processes-1/1.0')


OGC_DATATYPE_URL = f"{OGC_OPENGIS_URL}/def/dataType/OGC"

# See https://defs.opengis.net/vocprez/search?search=dataType&from=all
OgcDataType = MappingProxyType({
    # 0
    'double': f"{OGC_DATATYPE_URL}/0/double",
    'float128': f"{OGC_DATATYPE_URL}/0/float128",
    'float64': f"{OGC_DATATYPE_URL}/0/float64",
    'float32': f"{OGC_DATATYPE_URL}/0/float32",
    'float16': f"{OGC_DATATYPE_URL}/0/float16",
    'signedByte': f"{OGC_DATATYPE_URL}/0/signedByte",
    'signedInt': f"{OGC_DATATYPE_URL}/0/signedInt",
    'signedLong': f"{OGC_DATATYPE_URL}/0/signedLong",
    'signedShort': f"{OGC_DATATYPE_URL}/0/unsignedShort",
    'unsignedByte': f"{OGC_DATATYPE_URL}/0/unsignedByte",
    'unsignedInt': f"{OGC_DATATYPE_URL}/0/unsignedInt",
    'unsignedLong': f"{OGC_DATATYPE_URL}/0/unsignedLong",
    'unsignedShort': f"{OGC_DATATYPE_URL}/0/unsignedShort",
    'strinfg-utf8': f"{OGC_DATATYPE_URL}/0/string-utf8",
    # 1.1
    'angle': f"{OGC_DATATYPE_URL}/1.1/angle",
    'angleList': f"{OGC_DATATYPE_URL}/1.1/angleList",
    'anyCRS': f"{OGC_DATATYPE_URL}/1.1/anyCRS",
    'anyURI': f"{OGC_DATATYPE_URL}/1.1/anyURI",
    'boolean':  f"{OGC_DATATYPE_URL}/1.1/boolean",
    'crsURI': f"{OGC_DATATYPE_URL}/1.1/crsURI",
    'gridLength': f"{OGC_DATATYPE_URL}/1.1/gridLength",
    'gridLengthList': f"{OGC_DATATYPE_URL}/1.1/gridLengthList",
    'integerList': f"{OGC_DATATYPE_URL}/1.1/integerList",
    'length': f"{OGC_DATATYPE_URL}/1.1/length",
    'lengthList': f"{OGC_DATATYPE_URL}/1.1/lengthList",
    'lengthOrAngle': f"{OGC_DATATYPE_URL}/1.1/lengthOrAngle",
    'measure': f"{OGC_DATATYPE_URL}/1.1/measure",
    'measureList': f"{OGC_DATATYPE_URL}/1.1/measureList",
    'nonNegativeInteger':  f"{OGC_DATATYPE_URL}/1.1/nonNegativeInteger",
    'positiveInteger':  f"{OGC_DATATYPE_URL}/1.1/positiveInteger",
    'positiveIntegerList':  f"{OGC_DATATYPE_URL}/1.1/positiveIntegerList",
    'scale': f"{OGC_DATATYPE_URL}/1.1/scale",
    'scaleList': f"{OGC_DATATYPE_URL}/1.1/scaleList",
    'string': f"{OGC_DATATYPE_URL}/1.1/string",
    'time': f"{OGC_DATATYPE_URL}/1.1/time",
    'timeList': f"{OGC_DATATYPE_URL}/1.1/timeList",
    'valueFile': f"{OGC_DATATYPE_URL}/1.1/valueFile",
})


# For UCUM references,
# see
# * https://ucum.org/ucum
# * https://github.com/ucum-org/ucum
# * https://github.com/ucum-org/ucum/blob/main/ucum-essence.xml


OGC_UOM_URL = f"{OGC_OPENGIS_URL}/def/uom"
OGC_UOM_URN = "urn:ogc:def:uom"

UCUM = f"{OGC_UOM_URN}:UCUM"
OGC_UOM = f"{OGC_UOM_URN}:OGC:1.0"

UOM = MappingProxyType({
    'deg': (UCUM, 'deg'),
    'degree': (UCUM, 'deg'),
    'degrees': (UCUM, 'deg'),
    'inches': (UCUM, '[in_i]'),
    'meter': (UCUM, 'm'),
    'metre': (UCUM, 'm'),
    'metres': (UCUM, 'm'),
    'meters': (UCUM, 'm'),
    'm': (UCUM, 'm'),
    'feet': (UCUM, 'foot'),
    'radians': (UCUM, 'rad'),
    'radian': (UCUM, 'rad'),
    'rad': (UCUM, 'rad'),
    'kilometer': (UCUM, 'km'),
    'kilometers': (UCUM, 'km'),
    'km': (UCUM, 'km'),
    'centimeter': (UCUM, 'cm'),
    'centimeters': (UCUM, 'cm'),
    'cm': (UCUM, 'cm'),
    'millimeter': (UCUM, 'mm'),
    'millimeters': (UCUM, 'mm'),
    'mm': (UCUM, 'mm'),
    'mile': (UCUM, '[mi_i]'),
    'miles': (UCUM, '[mi_i]'),
    'nautical mile': (UCUM, '[nmi_i]'),
    'nautical miles': (UCUM, '[nmi_i]'),
    'yard': (UCUM, '[yd_i]'),
    'yards': (UCUM, '[yd_i]'),
    'yd': (UCUM, '[yd_i]'),
    'urn:ogc:def:uom:OGC:1.0:metre': (UCUM, 'm'),
    'urn:ogc:def:uom:OGC:1.0:degree': (UCUM, 'deg'),
    'urn:ogc:def:uom:OGC:1.0:radian': (UCUM, 'rad'),
    'urn:ogc:def:uom:OGC:1.0:feet': (UCUM, 'foot'),
    'unity': (OGC_UOM, 'unity'),
    'gridspacing': (OGC_UOM, 'gridspacing'),
    # Temporal units
    'week': (UCUM, 'wk'),
    'weeks': (UCUM, 'wk'),
    'years': (UCUM, 'a'),
    'day': (UCUM, 'd'),
    'days': (UCUM, 'd'),
    'month': (UCUM, 'mo'),
    'months': (UCUM, 'mo'),
    'hour': (UCUM, 'h'),
    'hours': (UCUM, 'h'),
    'min': (UCUM, 'min'),
    'minute': (UCUM, 'min'),
    'minutes': (UCUM, 'min'),
    's': (UCUM, 's'),
    'second': (UCUM, 's'),
    'seconds': (UCUM, 's'),
    'ms': (UCUM, 'ms'),
    'millisecond': (UCUM, 'ms'),
    'milliseconds': (UCUM, 'ms'),
    'decades': (UCUM, '10.a'),
    'centuries': (UCUM, '100.a'),
})


# CRSs

# Crs references may by either urn string or Url
CRSRef = str | HttpUrl


def crs_ref(
    auth_code: int | str,
    auth_name: str,
    *,
    version: Optional[str] = None,
) -> str:
    # Version is not required
    if version:
        return f"urn:ogc:def:crs:{auth_name}:{version}:{auth_code}"
    else:
        return f"urn:ogc:def:crs:{auth_name}:{auth_code}"


def crs_ref_from_epsg(code: int | str) -> str:
    return crs_ref(code, "EPSG")


def crs_definition_url(ref: str) -> HttpUrl:
    """  URL to the GML definition
    """
    path = ref.removeprefix('urn:ogc:').replace(':', '/')
    return HttpUrl(f"{OGC_OPENGIS_URL}/{path}")


# Default crss definitions
WGS84 = crs_ref("CRS84", "OGC", version="1.3")


# UOMs

UOMRef = str | HttpUrl


def uom_ref(name: str) -> Optional[str]:
    urn = UOM.get(name)
    return f"{urn[0]}:{urn[1]}" if urn else None
