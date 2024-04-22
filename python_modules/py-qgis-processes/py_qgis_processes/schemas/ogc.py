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
    GetCoreSchemaHandler,
)
from pydantic_core import CoreSchema, core_schema
from typing_extensions import Any, Optional, Self, Tuple, Type

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
    'integer': f"{OGC_DATATYPE_URL}/1.1/integer",
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

OGC_UOM = MappingProxyType({
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
})


class CrsRef(AnyUrl):

    @classmethod
    def __get_pydantic_core_schema__(
        cls: Type[Self], source_type: Any, handler: GetCoreSchemaHandler,  # noqa ANN401
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(AnyUrl))

    @classmethod
    def new(cls: Type[Self], auth_code: int | str, auth_name: str = "OGC", version: str = "1.3") -> Self:
        return cls(f"{OGC_OPENGIS_URL}/def/crs/{auth_name}/{version}/{auth_code}")

    @classmethod
    def from_epsg(cls: Type[Self], code: int) -> Self:
        return cls.new(code, "EPSG", version="9.9.1")

    @classmethod
    def wgs84(cls: Type[Self]) -> Self:
        return cls.new("CRS84")


class UOMRef(AnyUrl):

    @staticmethod
    def ref(name: str) -> Optional[Tuple[str, str]]:
        return OGC_UOM.get(name)

    @classmethod
    def __get_pydantic_core_schema__(
        cls: Type[Self], source_type: Any, handler: GetCoreSchemaHandler,  # noqa ANN401
    ) -> CoreSchema:
        return core_schema.no_info_after_validator_function(cls, handler(AnyUrl))

    @classmethod
    def from_name(cls: Type[Self], name: str) -> Optional[Self]:
        urn = OGC_UOM.get(name)
        if urn:
            return cls(f"{urn[0]}:{urn[1]}")
        else:
            return None
