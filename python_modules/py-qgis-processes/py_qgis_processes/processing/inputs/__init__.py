from types import MappingProxyType

from typing_extensions import Optional

from qgis.core import (
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterColor,
    QgsProcessingParameterCrs,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterDistance,
    QgsProcessingParameterDuration,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterGeometry,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMeshLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
    QgsProcessingParameterPointCloudDestination,
    QgsProcessingParameterPointCloudLayer,
    QgsProcessingParameterRange,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterScale,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterVectorTileDestination,
    QgsProcessingParameterVectorTileWriterLayers,
    QgsProject,
)

from .base import (
    InputParameter as InputParameterBase,
)
from .base import (
    ParameterDefinition,
    ProcessingConfig,
)
from .files import (
    ParameterFile,
    ParameterFileDestination,
    ParameterFolderDestination,
)
from .geometry import (
    ParameterCrs,
    ParameterExtent,
    ParameterGeometry,
    ParameterPoint,
)
from .layers import (
    ParameterFeatureSink,
    ParameterFeatureSource,
    ParameterMapLayer,
    ParameterMeshLayer,
    ParameterMultipleLayers,
    ParameterPointCloudDestination,
    ParameterPointCloudLayer,
    ParameterRasterDestination,
    ParameterRasterLayer,
    ParameterVectorDestination,
    ParameterVectorLayer,
    ParameterVectorTileDestination,
    ParameterVectorTileWriterLayers,
)
from .literal import (
    ParameterBand,
    ParameterBool,
    ParameterColor,
    ParameterDateTime,
    ParameterDistance,
    ParameterDuration,
    ParameterEnum,
    ParameterField,
    ParameterNumber,
    ParameterRange,
    ParameterScale,
    ParameterString,
)

# Type mapping

QGIS_TYPES = MappingProxyType({
    QgsProcessingParameterBand.typeName(): ParameterBand,
    QgsProcessingParameterBoolean.typeName(): ParameterBool,
    QgsProcessingParameterColor.typeName(): ParameterColor,
    # ParameterType.CoordinateOperation
    QgsProcessingParameterCrs.typeName(): ParameterCrs,
    # ParameterType.DatabaseSchema
    # ParameterType.DatabaseTable
    QgsProcessingParameterDateTime.typeName(): ParameterDateTime,
    # ParameterType.DxfLayers
    QgsProcessingParameterEnum.typeName(): ParameterEnum,
    # ParameterType.Expression
    QgsProcessingParameterExtent.typeName(): ParameterExtent,
    QgsProcessingParameterFeatureSource.typeName(): ParameterFeatureSource,
    QgsProcessingParameterField.typeName(): ParameterField,
    # ParameterType.FieldMapping
    QgsProcessingParameterFile.typeName(): ParameterFile,
    QgsProcessingParameterGeometry.typeName(): ParameterGeometry,
    # ParameterType.Layout
    # ParameterType.LayoutItem
    QgsProcessingParameterMapLayer.typeName(): ParameterMapLayer,
    # ParameterType.MapTheme
    # ParameterType.Matrix
    # ParameterType.MeshDatasetGroups
    # ParameterType.MeshDatasetTime
    QgsProcessingParameterMeshLayer.typeName(): ParameterMeshLayer,
    QgsProcessingParameterMultipleLayers.typeName(): ParameterMultipleLayers,
    QgsProcessingParameterNumber.typeName(): ParameterNumber,
    QgsProcessingParameterDistance.typeName(): ParameterDistance,
    QgsProcessingParameterDuration.typeName(): ParameterDuration,
    QgsProcessingParameterScale.typeName(): ParameterScale,
    QgsProcessingParameterPoint.typeName(): ParameterPoint,
    QgsProcessingParameterPointCloudLayer.typeName(): ParameterPointCloudLayer,
    # ParameterType.ProviderConnection
    QgsProcessingParameterRange.typeName(): ParameterRange,
    QgsProcessingParameterRasterLayer.typeName(): ParameterRasterLayer,
    QgsProcessingParameterString.typeName(): ParameterString,
    # ParameterType.TinInputLayers
    QgsProcessingParameterVectorLayer.typeName(): ParameterVectorLayer,
    QgsProcessingParameterVectorTileWriterLayers.typeName(): ParameterVectorTileWriterLayers,
    QgsProcessingParameterFeatureSink.typeName(): ParameterFeatureSink,
    QgsProcessingParameterFileDestination.typeName(): ParameterFileDestination,
    QgsProcessingParameterFolderDestination.typeName(): ParameterFolderDestination,
    QgsProcessingParameterPointCloudDestination.typeName(): ParameterPointCloudDestination,
    QgsProcessingParameterRasterDestination.typeName(): ParameterRasterDestination,
    QgsProcessingParameterVectorDestination.typeName(): ParameterVectorDestination,
    QgsProcessingParameterVectorTileDestination.typeName(): ParameterVectorTileDestination,
    # ParameterType.Aggregate
    # ParameterType.AlignRasterLayers
})


def InputParameter(
        param: ParameterDefinition,
        project: Optional[QgsProject] = None,
        *,
        config: Optional[ProcessingConfig] = None,
    ) -> InputParameterBase:

    Input = QGIS_TYPES.get(param.type())
    if Input is None:
        raise ValueError(f"Unsupported parameter: {param}")

    return Input(param, project, config=config)
