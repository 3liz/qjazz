
import re

from osgeo import ogr
from pydantic import (
    AnyUrl,
    Field,
    JsonValue,
    TypeAdapter,
)
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    Iterator,
    Optional,
    Sequence,
    Type,
    TypeAlias,
    Union,
)

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingParameterCrs,
    QgsProcessingParameterExtent,
    QgsProcessingParameterGeometry,
    QgsProcessingParameterPoint,
    QgsProcessingParameters,
    QgsProject,
    QgsRectangle,
    QgsReferencedGeometry,
    QgsReferencedPointXY,
    QgsReferencedRectangle,
    QgsWkbTypes,
)

from py_qgis_contrib.core import logger
from py_qgis_processes_schemas import (
    WGS84,
    BoundingBox,
    Formats,
    InputValueError,
    MediaType,
    OneOf,
    geojson,
)

from .base import (
    InputParameter,
    ParameterDefinition,
    ProcessingContext,
)

#
# QgsProcessingParameterGeometry
#


def geometrytypes_to_model(
    seq: Sequence[Qgis.GeometryType],
    allowMultipart: bool,
) -> Iterator[TypeAlias]:
    for t in seq:
        match t:
            case Qgis.GeometryType.Point:
                yield geojson.Point
                if allowMultipart:
                    yield geojson.MultiPoint
            case Qgis.GeometryType.Line:
                yield geojson.LineString
                if allowMultipart:
                    yield geojson.MultiLineString
            case Qgis.GeometryType.Polygon:
                yield geojson.Polygon
                if allowMultipart:
                    yield geojson.MultiPolygon


class ParameterGeometry(InputParameter):

    @classmethod
    def get_geometry_type(cls, param: QgsProcessingParameterGeometry) -> TypeAlias:
        geomtypes = param.geometryTypes()
        if geomtypes:
            return Union[tuple(geometrytypes_to_model(geomtypes, param.allowMultipart()))]
        else:
            return geojson.Geometry

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = cls.get_geometry_type(param)
        if not validation_only:
            default = field.pop('default', None)
            g = default and qgsgeometry_to_json(_type, default, project and project.crs())
            if g:
                field.update(default=g)

            _type = Annotated[
                _type,
                Field(json_schema_extra={'format': 'geojson-schema'}),
            ]

        _type = OneOf[   # type: ignore [misc, valid-type]
            Union[
                _type,
                MediaType(str, Formats.WKT.media_type),
                MediaType(str, Formats.GML.media_type),
            ],
        ]

        return _type

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> QgsGeometry:

        # Check for qualified input
        match inp:
            case {'value': str(value), 'mediaType': media_type, **_rest}:
                match media_type:
                    case Formats.WKT.media_type:
                        geom = wkt_to_geometry(value)
                    case Formats.GML.media_type:
                        geom = gml_to_geometry(value)
                    case invalid:
                        raise InputValueError(f"Invalid geometry format: {invalid}")
            case _:
                # GeoJson
                _inp = self.validate(inp)
                geom = ogr.CreateGeometryFromJson(_inp.model_dump_json())
                if geom:
                    # XXX There is no method for direct import
                    # from json
                    geom = QgsGeometry.fromWkt(geom.ExportToWkt())
                    crs = QgsCoordinateReferenceSystem()
                    if _inp.crs:
                        crs.createFromUserInput(_inp.crs.name())
                        if crs.isValid():
                            geom = QgsReferencedGeometry(geom, crs)
                        else:
                            logger.error("Invalid CRS for geometry: %s", _inp.crs.name())

        return geom


#
# QgsProcessingParameterPoint
#

class ParameterPoint(ParameterGeometry):

    @classmethod
    def get_geometry_type(cls, _: QgsProcessingParameterPoint) -> TypeAlias:
        return geojson.Point

    def value(
        self, inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QgsReferencedPointXY | QgsPointXY:

        g = super().value(inp, context)
        match g:
            case QgsReferencedGeometry():
                p = qgsgeometry_to_point(g, g.crs())
            case QgsGeometry():
                p = qgsgeometry_to_point(g)
            case _:
                raise InputValueError("Geometry expected")

        return p


#
# QgsProcessingParameterCrs
#
CrsDefinition = OneOf[   # type: ignore [misc, valid-type]
    Union[
        str,
        AnyUrl,
        MediaType(str, Formats.WKT.media_type),
        MediaType(str, Formats.GML.media_type),
    ],
]


class ParameterCrs(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterCrs,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        if not validation_only:
            default = field.pop('default', None)
            if default:
                context = QgsProcessingContext()
                if project:
                    context.setProject(project)

                crs = QgsProcessingParameters.parametrAsCrs(
                    param,
                    {param.name(): default},
                    context,
                )
                if crs.isValid:
                    field.update(default=crs.toOgcUrn())

            field.update(json_schema_extra={'format': "x-ogc-crs"})

            _type = CrsDefinition
        else:
            _type = str

        return _type

    def value(
        self, inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QgsCoordinateReferenceSystem:

        value = self.validate(inp)

        crs = QgsCoordinateReferenceSystem()
        crs.createFromUserInput(value)
        if not crs or not crs.isValid():
            raise InputValueError(f"Invalid CRS: {crs}")

        return crs


#
# QgsProcessingParameterCoordinateOperation
#

class ParameterCoordinateOperation(ParameterCrs):
    # Input is a coordinate reference system
    pass


#
# QgsProcessingParameterExtent
#

class ParameterExtent(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterExtent,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        if not validation_only:
            default = field.pop('default', None)
            if default:
                context = QgsProcessingContext()
                if project:
                    context.setProject(project)

                rect = QgsProcessingParameters.parameterAsExtent(
                    param,
                    {param.name(): default},
                    context,
                )

                crs = QgsProcessingParameters.parameterAsExtentCrs(
                    param,
                    {param.name(): default},
                    context,
                )

                default_crs = crs.toOgcUrn() if crs.isValid() else WGS84

                _type = BoundingBox(Annotated[CrsDefinition, Field(default_crs)])

                if not rect.isEmpty() or rect.isNull():
                    field.update(
                        default=TypeAdapter(_type).validate_python({
                            "bbox": [
                                rect.xMinimum(),
                                rect.yMinimum(),
                                rect.xMaximum(),
                                rect.yMaximum(),
                            ],
                        }).model_dump(mode='json', by_alias=True),
                    )
        else:
            _type = BoundingBox(str)

        return _type

    def value(
        self, inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QgsReferencedRectangle:

        value = self.validate(inp)

        bbox = value.bbox
        rect = QgsRectangle(bbox[0], bbox[1], bbox[2], bbox[3])

        crs = QgsCoordinateReferenceSystem()
        crs.createFromUserInput(value.crs)

        return QgsReferencedRectangle(rect, crs)


#
# Utils
#


def qgsgeometry_to_point(
    g: QgsGeometry,
    crs: Optional[QgsCoordinateReferenceSystem] = None,
) -> QgsPointXY | QgsReferencedPointXY:

    if g.wkbType() == QgsWkbTypes.Point:
        p = g.asPoint()
    else:
        p = g.centroid().asPoint()

    return QgsReferencedPointXY(p, crs) if crs else p


def crs_to_ogc_urn(crs: QgsCoordinateReferenceSystem) -> str:
    if Qgis.QGIS_VERSION_INT >= 33800:
        return crs.toOgcUrn()
    else:
        path = (AnyUrl(crs.toOgcUri()).path or "").strip('/').replace('/', ':')
        return f"urn:ogc:{path}"


def qgsgeometry_to_json(
    GeometryType: TypeAlias,
    g: QgsPointXY | QgsReferencedPointXY | QgsGeometry | QgsReferencedGeometry,
    default_crs: Optional[QgsCoordinateReferenceSystem] = None,
) -> Optional[geojson.Geometry]:
    """ Convert Qgis geometry to GeoJson object
    """
    out: Any
    match g:
        case QgsReferencedPointXY(g):
            crs = g.crs()
            out = geojson.Point.from_xy(g.x(), g.y())
        case QgsPointXY(g):
            crs = QgsCoordinateReferenceSystem()
            out = geojson.Point.from_xy(g.x(), g.y())
        case QgsReferencedGeometry(g):
            crs = g.crs()
            out = TypeAdapter(GeometryType).validate_json(g.asJson())
        case QgsGeometry():
            crs = QgsCoordinateReferenceSystem()
            out = TypeAdapter(GeometryType).validate_json(g.asJson())
        case _:
            out = None

    if out:
        if default_crs and not crs.isValid():
            crs = default_crs
        if crs.isValid():
            out.crs = geojson.NamedCrs.from_ref(crs_to_ogc_urn(crs))

    return out


WKT_EXPR = re.compile(r"^\s*(?:(CRS|SRID)=(.*);)?(.*?)$")


def wkt_to_geometry(wkt: str) -> QgsGeometry | QgsReferencedGeometry:
    """ Convert wkt to qgis geometry

        Handle CRS= prefix
    """
    m = WKT_EXPR.match(wkt)
    if m:
        g = QgsGeometry.fromWkt(m.groups('')[2])
        if not g.isNull():
            crs_str = m.groups('')[1]
            if m.groups('')[0] == 'SRID':
                crs_str = f'POSTGIS:{crs_str}'

            crs = QgsCoordinateReferenceSystem(crs_str)
            if crs.isValid():
                g = QgsReferencedGeometry(g, crs)
        return g
    raise InputValueError("Invalid wkt format")


SRSNAME_EXPR = re.compile(r'\bsrsname\b="([^"]+)"', re.IGNORECASE)


def gml_to_geometry(gml: str) -> QgsGeometry | QgsReferencedGeometry:
    """ Handle json to qgis geometry
    """
    # Lookup for srsName
    geom = ogr.CreateGeometryFromGML(gml)
    if not geom:
        raise InputValueError("Invalid gml format")

    geom = QgsGeometry.fromWkt(geom.ExportToWkt())
    # Check for crs
    m = SRSNAME_EXPR.search(gml)
    if m:
        crs = QgsCoordinateReferenceSystem(m.groups('')[0])
        if crs.isValid():
            geom = QgsReferencedGeometry(geom, crs)
    return geom
