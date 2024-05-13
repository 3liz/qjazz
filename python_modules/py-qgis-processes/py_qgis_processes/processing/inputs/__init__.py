from types import MappingProxyType

from typing_extensions import Optional

from qgis.core import (
    QgsProcessingParameterAggregate,
    QgsProcessingParameterAlignRasterLayers,
    QgsProcessingParameterAnnotationLayer,
    QgsProcessingParameterBand,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterColor,
    QgsProcessingParameterCoordinateOperation,
    QgsProcessingParameterCrs,
    QgsProcessingParameterDatabaseSchema,
    QgsProcessingParameterDatabaseTable,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterDistance,
    QgsProcessingParameterDuration,
    QgsProcessingParameterDxfLayers,
    QgsProcessingParameterEnum,
    QgsProcessingParameterExpression,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFieldMapping,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterGeometry,
    QgsProcessingParameterLayout,
    QgsProcessingParameterLayoutItem,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMapTheme,
    QgsProcessingParameterMatrix,
    QgsProcessingParameterMeshDatasetGroups,
    QgsProcessingParameterMeshDatasetTime,
    QgsProcessingParameterMeshLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterPoint,
    QgsProcessingParameterPointCloudDestination,
    QgsProcessingParameterPointCloudLayer,
    QgsProcessingParameterProviderConnection,
    QgsProcessingParameterRange,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterScale,
    QgsProcessingParameterString,
    QgsProcessingParameterTinInputLayers,
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
from .datetime import (
    ParameterDateTime,
)
from .files import (
    ParameterFile,
    ParameterFileDestination,
    ParameterFolderDestination,
)
from .geometry import (
    ParameterCoordinateOperation,
    ParameterCrs,
    ParameterExtent,
    ParameterGeometry,
    ParameterPoint,
)
from .layers import (
    ParameterAggregate,
    ParameterAlignRasterLayers,
    ParameterAnnotationLayer,
    ParameterBand,
    ParameterDxfLayers,
    ParameterExpression,
    ParameterFeatureSink,
    ParameterFeatureSource,
    ParameterField,
    ParameterFieldMapping,
    ParameterMapLayer,
    ParameterMultipleLayers,
    ParameterPointCloudDestination,
    ParameterPointCloudLayer,
    ParameterRasterDestination,
    ParameterRasterLayer,
    ParameterTinInputLayers,
    ParameterVectorDestination,
    ParameterVectorLayer,
    ParameterVectorTileDestination,
    ParameterVectorTileWriterLayers,
)
from .literal import (
    ParameterBool,
    ParameterColor,
    ParameterDatabaseSchema,
    ParameterDatabaseTable,
    ParameterDistance,
    ParameterDuration,
    ParameterEnum,
    ParameterLayout,
    ParameterLayoutItem,
    ParameterMapTheme,
    ParameterNumber,
    ParameterProviderConnection,
    ParameterRange,
    ParameterScale,
    ParameterString,
)
from .matrix import ParameterMatrix
from .mesh import (
    ParameterMeshDatasetGroups,
    ParameterMeshDatasetTime,
    ParameterMeshLayer,
)

# Type mapping

QGIS_TYPES = MappingProxyType({
    QgsProcessingParameterAggregate.typeName(): ParameterAggregate,
    QgsProcessingParameterAlignRasterLayers.typeName(): ParameterAlignRasterLayers,
    QgsProcessingParameterAnnotationLayer.typeName(): ParameterAnnotationLayer,
    QgsProcessingParameterBand.typeName(): ParameterBand,
    QgsProcessingParameterBoolean.typeName(): ParameterBool,
    QgsProcessingParameterColor.typeName(): ParameterColor,
    QgsProcessingParameterCoordinateOperation: ParameterCoordinateOperation,
    QgsProcessingParameterCrs.typeName(): ParameterCrs,
    QgsProcessingParameterDatabaseSchema.typeName(): ParameterDatabaseSchema,
    QgsProcessingParameterDatabaseTable.typeName(): ParameterDatabaseTable,
    QgsProcessingParameterDateTime.typeName(): ParameterDateTime,
    QgsProcessingParameterDxfLayers.typeName(): ParameterDxfLayers,
    QgsProcessingParameterEnum.typeName(): ParameterEnum,
    QgsProcessingParameterExpression.typeName(): ParameterExpression,
    QgsProcessingParameterExtent.typeName(): ParameterExtent,
    QgsProcessingParameterFeatureSource.typeName(): ParameterFeatureSource,
    QgsProcessingParameterField.typeName(): ParameterField,
    QgsProcessingParameterFieldMapping.typeName(): ParameterFieldMapping,
    QgsProcessingParameterFile.typeName(): ParameterFile,
    QgsProcessingParameterGeometry.typeName(): ParameterGeometry,
    QgsProcessingParameterLayout.typeName(): ParameterLayout,
    QgsProcessingParameterLayoutItem.typeName(): ParameterLayoutItem,
    QgsProcessingParameterMapLayer.typeName(): ParameterMapLayer,
    QgsProcessingParameterMapTheme.typeName(): ParameterMapTheme,
    QgsProcessingParameterMatrix.typeName(): ParameterMatrix,
    QgsProcessingParameterMeshDatasetGroups.typeName(): ParameterMeshDatasetGroups,
    QgsProcessingParameterMeshDatasetTime.typeName(): ParameterMeshDatasetTime,
    QgsProcessingParameterMeshLayer.typeName(): ParameterMeshLayer,
    QgsProcessingParameterMultipleLayers.typeName(): ParameterMultipleLayers,
    QgsProcessingParameterNumber.typeName(): ParameterNumber,
    QgsProcessingParameterDistance.typeName(): ParameterDistance,
    QgsProcessingParameterDuration.typeName(): ParameterDuration,
    QgsProcessingParameterScale.typeName(): ParameterScale,
    QgsProcessingParameterPoint.typeName(): ParameterPoint,
    QgsProcessingParameterPointCloudLayer.typeName(): ParameterPointCloudLayer,
    QgsProcessingParameterProviderConnection.typeName(): ParameterProviderConnection,
    QgsProcessingParameterRange.typeName(): ParameterRange,
    QgsProcessingParameterRasterLayer.typeName(): ParameterRasterLayer,
    QgsProcessingParameterString.typeName(): ParameterString,
    QgsProcessingParameterTinInputLayers.typeName(): ParameterTinInputLayers,
    QgsProcessingParameterVectorLayer.typeName(): ParameterVectorLayer,
    QgsProcessingParameterVectorTileWriterLayers.typeName(): ParameterVectorTileWriterLayers,
    QgsProcessingParameterFeatureSink.typeName(): ParameterFeatureSink,
    QgsProcessingParameterFileDestination.typeName(): ParameterFileDestination,
    QgsProcessingParameterFolderDestination.typeName(): ParameterFolderDestination,
    QgsProcessingParameterPointCloudDestination.typeName(): ParameterPointCloudDestination,
    QgsProcessingParameterRasterDestination.typeName(): ParameterRasterDestination,
    QgsProcessingParameterVectorDestination.typeName(): ParameterVectorDestination,
    QgsProcessingParameterVectorTileDestination.typeName(): ParameterVectorTileDestination,
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
