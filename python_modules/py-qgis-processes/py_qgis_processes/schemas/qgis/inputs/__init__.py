from types import MappingProxyType

from qgis.core import (
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDistance,
    # QgsProcessingParameterDuration,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRange,
    QgsProcessingParameterScale,
    QgsProcessingParameterString,
    QgsProject,
)
from typing_extensions import Optional

from .base import InputParameter as InputParameterBase
from .base import ParameterDefinition
from .literal import (
    ParameterBool,
    ParameterDistance,
    ParameterEnum,
    ParameterNumber,
    ParameterRange,
    ParameterScale,
    ParameterString,
)

# Type mapping

QGIS_TYPES = MappingProxyType({
    # ParameterType.Band
    QgsProcessingParameterBoolean.typeName(): ParameterBool,
    # ParameterType.Color
    # ParameterType.CoordinateOperation
    # ParameterType.Crs
    # ParameterType.DatabaseSchema
    # ParameterType.DatabaseTable
    # ParameterType.DateTime
    # ParameterType.DxfLayers
    QgsProcessingParameterEnum.typeName(): ParameterEnum,
    # ParameterType.Expression
    # ParameterType.Extent
    # ParameterType.FeatureSource
    # ParameterType.Field
    # ParameterType.FieldMapping
    # ParameterType.File
    # ParameterType.Geometry
    # ParameterType.Layout
    # ParameterType.LayoutItem
    # ParameterType.MapLayer
    # ParameterType.MapTheme
    # ParameterType.Matrix
    # ParameterType.MeshDatasetGroups
    # ParameterType.MeshDatasetTime
    # ParameterType.MeshLayer
    # ParameterType.MultipleLayers
    QgsProcessingParameterNumber.typeName(): ParameterNumber,
    QgsProcessingParameterDistance.typeName(): ParameterDistance,
    # QgsProcessingParameterDuration.typeName(): ParameterDuration,
    QgsProcessingParameterScale.typeName(): ParameterScale,
    # ParameterType.Point
    # ParameterType.PointCloudLayer
    # ParameterType.ProviderConnection
    QgsProcessingParameterRange.typeName(): ParameterRange,
    # ParameterType.RasterLayer
    QgsProcessingParameterString.typeName(): ParameterString,
    # ParameterType.TinInputLayers
    # ParameterType.VectorLayer
    # ParameterType.VectorTileWriterLayers
    # ParameterType.FeatureSink
    # ParameterType.FileDestination
    # ParameterType.FolderDestination
    # ParameterType.PointCloudDestination
    # ParameterType.RasterDestination
    # ParameterType.VectorDestination
    # ParameterType.VectorTileDestination
    # ParameterType.Aggregate
    # ParameterType.AlignRasterLayers
})


def InputParameter(
        param: ParameterDefinition,
        project: Optional[QgsProject] = None,
    ) -> InputParameterBase:

    Input = QGIS_TYPES.get(param.type())
    if Input is None:
        raise ValueError(f"Unsupported parameter: {param}")

    return Input(param, project)
