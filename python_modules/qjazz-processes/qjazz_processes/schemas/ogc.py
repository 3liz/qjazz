#
# Copyright 2024 3liz
# Author: David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
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
EPSG_UOM = f"{OGC_UOM_URN}:ESPG:0:"

UOM = MappingProxyType({
    'deg': (UCUM, 'deg'),
    'degree': (UCUM, 'deg'),
    'degrees': (UCUM, 'deg'),
    'inches': (UCUM, '[in_i]'),
    'meter': (UCUM, 'm'),
    'metre': (UCUM, 'm'),
    'metres': (UCUM, 'm'),
    'meters': (UCUM, 'm'),
    'meters (German legal)': (EPSG_UOM, '9031'),
    'm': (UCUM, 'm'),
    'feet': (UCUM, 'foot'),
    'feet (British, 1865)': (EPSG_UOM, '9070'),
    'feet (British, 1936)': (EPSG_UOM, '9095'),
    'feet (British, Benoit 1895 A)': (EPSG_UOM, '9051'),
    'feet (British, Benoit 1895 B)': (EPSG_UOM, '9061'),
    'feet (British, Sears 1922)': (EPSG_UOM, '9041'),
    'feet (British, Sears 1922 truncated)': (EPSG_UOM, '9300'),
    "feet (Clarke's)": (EPSG_UOM, '9005'),
    'feet (Gold Coast)': (EPSG_UOM, '9094'),
    'feet (Indian)': (EPSG_UOM, '9080'),
    'feet (Indian 1937)': (EPSG_UOM, '9081'),
    'feet (Indian 1962)': (EPSG_UOM, '9082'),
    'feet (Indian 1975)': (EPSG_UOM, '9083'),
    'feet (US survey)': (EPSG_UOM, '9003'),
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
    'miles (US survey)': (EPSG_UOM, '9035'),
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
    'fathom': (UCUM, '[fth_i]'),
    'fathoms': (UCUM, '[fth_i]'),
    'yards (British, Sears 1922)': (EPSG_UOM, '9040'),
    'yards (British, Sears 1922 truncated)': (EPSG_UOM, '9099'),
    'yards (British, Benoit 1895 A)': (EPSG_UOM, '9050'),
    'yards (British, Benoit 1895 B)': (EPSG_UOM, '9060'),
    "yards (Clarke's)": (EPSG_UOM, '9037'),
    'yards (Indian)': (EPSG_UOM, '9084'),
    'yards (Indian 1937)': (EPSG_UOM, '9085'),
    'yards (Indian 1962)': (EPSG_UOM, '9086'),
    'yards (Indian 1975)': (EPSG_UOM, '9087'),
    'links (British, Benoit 1895 A)': (EPSG_UOM, '9053'),
    'links (British, Benoit 1895 B)': (EPSG_UOM, '9063'),
    'links (British, Sears 1922)': (EPSG_UOM, '9043'),
    'links (British, Sears 1922 truncated)': (EPSG_UOM, '9302'),
    "links (Clarke's)": (EPSG_UOM, '9039'),
    'links': (EPSG_UOM, '9098'),
    'link': (EPSG_UOM, '9098'),
    'links (US survey)': (EPSG_UOM, '9033'),
    'chains (British, Benoit 1895 A)': (EPSG_UOM, '9052'),
    'chains (British, Benoit 1895 B)': (EPSG_UOM, '9062'),
    'chains (British, Sears 1922)': (EPSG_UOM, '9042'),
    'chains (British, Sears 1922 truncated)': (EPSG_UOM, '9301'),
    "chains (Clarke's)": (EPSG_UOM, '9038'),
    'chains (international)': (EPSG_UOM, '9097'),
    'chains': (EPSG_UOM, '9097'),
    'chain': (EPSG_UOM, '9097'),
    'chains (US survey)': (EPSG_UOM, '9033'),
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
