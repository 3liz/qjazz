
import re
import traceback

from collections.abc import Container
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from typing_extensions import (
    Optional,
    Sequence,
    Tuple,
    Type,
)

from qgis.core import (
    Qgis,
    QgsMapLayer,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingDestinationParameter,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)

from py_qgis_contrib.core import logger
from py_qgis_processes_schemas import (
    InputValueError,
)

ProcessingSourceType: Type

if Qgis.QGIS_VERSION_INT >= 33600:
    # In qgis 3.36+ ProcessingSourceType is a real python enum
    ProcessingSourceType = Qgis.ProcessingSourceType
else:
    class _ProcessingSourceType(Enum):
        MapLayer = QgsProcessing.TypeMapLayer
        VectorAnyGeometry = QgsProcessing.TypeVectorAnyGeometry
        VectorPoint = QgsProcessing.TypeVectorPoint
        VectorLine = QgsProcessing.TypeVectorLine
        VectorPolygon = QgsProcessing.TypeVectorPolygon
        Raster = QgsProcessing.TypeRaster
        File = QgsProcessing.TypeFile
        Vector = QgsProcessing.TypeVector
        Mesh = QgsProcessing.TypeMesh
        Plugin = QgsProcessing.TypePlugin
        PointCloud = QgsProcessing.TypePointCloud
        Annotation = QgsProcessing.TypeAnnotation
        VectorTile = QgsProcessing.TypeVectorTile

    ProcessingSourceType = _ProcessingSourceType

LayerType = Qgis.LayerType


if Qgis.QGIS_VERSION_INT >= 33600:
    ProcessingFileParameterBehavior = Qgis.ProcessingFileParameterBehavior
else:
    from qgis.core import QgsProcessingParameterFile
    ProcessingFileParameterBehavior = QgsProcessingParameterFile.Behavior


#
# Utils
#
def get_valid_filename(s: str) -> str:
    """ Return a valid filename from input str

        Removes all characters which are not letters, not numbers (0-9),
        not the underscore ('_'), not the dash ('-'), and not the period ('.').
    """
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '_', s)


def filter_layer_from_context(
    layer: QgsMapLayer,
    sourcetypes: Container[ProcessingSourceType],  # type: ignore [valid-type]
    spatial: Optional[bool] = None,
) -> bool:
    """ Find candidate layers according to datatypes
    """
    if spatial is not None and layer.isSpatial() != spatial:
        return False

    match layer.type():
        case LayerType.Vector:
            match layer.geometryType():
                case QgsWkbTypes.PointGeometry:
                    return ProcessingSourceType.VectorPoint in sourcetypes
                case QgsWkbTypes.LineGeometry:
                    return ProcessingSourceType.VectorLine in sourcetypes
                case QgsWkbTypes.PointGeometry:
                    return ProcessingSourceType.VectorPolygon in sourcetypes
                case _:
                    return ProcessingSourceType.VectorAnyGeometry in sourcetypes \
                        or ProcessingSourceType.Vector in sourcetypes
        case LayerType.Raster:
            return ProcessingSourceType.Raster in sourcetypes
        case LayerType.Mesh:
            return ProcessingSourceType.Mesh in sourcetypes
        case LayerType.VectorTile:
            return ProcessingSourceType.VectorTile in sourcetypes
        case LayerType.Annotation:
            return ProcessingSourceType.Annotation in sourcetypes
        case LayerType.PointCloud:
            return ProcessingSourceType.PointCloud in sourcetypes
        # Group/Tiled scene have no corresponding processing
        # source type

    return False


def layer_names_from_context(
    project: QgsProject,
    sourcetypes: Container[ProcessingSourceType],  # type: ignore [valid-type]
    spatial: Optional[bool] = None,
) -> Sequence[str]:

    layers = (layer for layer in project.mapLayers().values())
    if ProcessingSourceType.MapLayer not in sourcetypes:
        layers = filter(   # type: ignore  [assignment]
            lambda layer: filter_layer_from_context(layer, sourcetypes, spatial),
            layers,
        )

    return tuple(layer.name() for layer in layers)


def parse_layer_spec(
    layerspec: str,
    context: Optional[QgsProcessingContext] = None,
    allow_selection: bool = False,
) -> Tuple[str, bool]:
    """ Parse a layer specification

        if allow_selection is set to True: 'select' parameter
        is interpreted has holding a qgis feature request expression

        :return: A tuple (path, bool)
    """
    if layerspec.find('layer:', 0, 6) == -1:
        # Nothing to do with it
        return layerspec, False

    u = urlsplit(layerspec)
    p = u.path

    if not (allow_selection and context):
        return p, False

    has_selection = False
    qs = parse_qs(u.query)
    feat_requests = qs.get('select', [])
    feat_rects = qs.get('rect', [])

    if feat_rects or feat_requests:

        has_selection = True
        layer = context.getMapLayer(p)

        if not layer:
            logger.error("No layer path for %s", layerspec)
            raise InputValueError("No layer '%s' found" % u.path)

        if layer.type() != QgsMapLayer.VectorLayer:
            logger.warning("Can apply selection only to vector layer")
        else:
            behavior = QgsVectorLayer.SetSelection
            try:
                logger.debug("Applying features selection: %s", qs)

                # Apply filter rect first
                if feat_rects:
                    rect = QgsRectangle(feat_rects[-1].split(',')[:4])
                    layer.selectByRect(rect, behavior=behavior)
                    behavior = QgsVectorLayer.IntersectSelection

                # Selection by expressions
                if feat_requests:
                    ftreq = feat_requests[-1]
                    layer.selectByExpression(ftreq, behavior=behavior)
            except Exception:
                logger.error(traceback.format_exc())
                raise
    return p, has_selection


def raw_destination_sink(
    param: QgsProcessingDestinationParameter,
    destination: str,
    default_extension: str,
    root_path: Optional[Path],
) -> Tuple[str, str]:
    #
    # Parse input value as sink
    #
    # In this situation, value is interpreted as the output sink of the destination layer,
    # It may be any source url supported by Qgis (but with options stripped)
    #
    # The layername may be specified by appending the '|layername=<name>' to the input string.
    #
    destination, *rest = destination.split('|', 2)

    destinationName = None

    # Check for layername option
    if len(rest) > 0 and rest[0].lower().startswith('layername='):
        destinationName = rest[0].split('=')[1].strip()

    url = urlsplit(destination)
    if url.path and url.scheme.lower() in ('', 'file'):
        p = Path(url.path)

        if p.is_absolute():
            p = p.relative_to('/')
            if root_path:
                p = root_path.joinpath(p)

        # Check for extension:
        if not p.suffix:
            p = p.with_suffix(f'.{default_extension}')

        destinationName = destinationName or p.stem
        sink = str(p)
    else:
        destinationName = destinationName or param.name()
        sink = destination

    return sink, destinationName
