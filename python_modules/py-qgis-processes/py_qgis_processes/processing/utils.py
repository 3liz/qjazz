
import re
import traceback

from collections.abc import Container
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from typing_extensions import (
    Iterable,
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
    QgsProcessingParameterFileDestination,
    QgsProcessingUtils,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)

from py_qgis_contrib.core import logger
from py_qgis_processes_schemas import (
    Format,
    InputValueError,
    mimetypes,
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
def compatible_layers(
    project: QgsProject,
    dtypes: Container[ProcessingSourceType],  # type: ignore [valid-type]
) -> Iterable[QgsMapLayer]:
    if dtypes:
        layers = QgsProcessingUtils.compatibleVectorLayers(project, dtypes)
        if ProcessingSourceType.Raster in dtypes:
            layers.extend(QgsProcessingUtils.compatibleRasterLayers(project))
        if ProcessingSourceType.Mesh in dtypes:
            layers.extend(QgsProcessingUtils.compatibleMeshLayers(project))
        if ProcessingSourceType.Annotation in dtypes:
            layers.extend(QgsProcessingUtils.compatibleAnnotationLayers(project))
        if ProcessingSourceType.VectorTile in dtypes:
            layers.extend(QgsProcessingUtils.compatibleVectoTileLayers(project))
        if ProcessingSourceType.PointCloud in dtypes:
            layers.extend(QgsProcessingUtils.compatiblePointCloudLayers(project))
        return layers
    else:
        return QgsProcessingUtils.compatibleLayers(project)


def get_valid_filename(s: str) -> str:
    """ Return a valid filename from input str

        Removes all characters which are not letters, not numbers (0-9),
        not the underscore ('_'), not the dash ('-'), and not the period ('.').
    """
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '_', s)


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
    if not layerspec.startswith('layer:'):
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


def resolve_raw_path(
    p: str,
    workdir: Path,
    root_path: Optional[Path],
    extension: str,
) -> Path:
    #
    # Resolve raw path
    #
    p = Path(p)
    # Absolute path are stored in root folder
    if p.is_absolute():
        p = p.relative_to('/')
        if root_path:
            p = root_path.joinpath(p)
    else:
        p = workdir.joinpath(p)

    # Check for extension:
    if extension and not p.suffix:
        p = p.with_suffix(extension)

    return p


def resolve_raw_reference(
    ref: str,
    workdir: Path,
    root_path: Optional[Path],
    extension: str,
) -> Optional[Path]:
    #
    # Resolve raw reference
    #
    path: Optional[Path] = None
    url = urlsplit(ref)
    if url.path and url.scheme.lower() == 'file':
        path = resolve_raw_path(url.path, workdir, root_path, extension)

    return path


def raw_destination_sink(
    param: QgsProcessingDestinationParameter,
    destination: str,
    workdir: Path,
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
        p = resolve_raw_path(url.path, workdir, root_path, default_extension)
        destinationName = destinationName or p.stem
        sink = str(p)
    else:
        destinationName = destinationName or param.name()
        sink = destination

    return sink, destinationName


def output_file_formats(param: QgsProcessingParameterFileDestination) -> Sequence[Format]:
    #
    # Retrieve format list from file extensions
    #
    formats = []
    ext_re = re.compile(r'.*([.][a-z]+)')
    for filter_ in param.fileFilter().split(";;"):
        m = ext_re.match(filter_)
        if m:
            ext = m.group(1)
            mime = mimetypes.types_map.get(ext)
            if mime:
                formats.append(Format(media_type=mime, suffix=ext))

    return formats
