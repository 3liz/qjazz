from types import MappingProxyType

from pydantic import ValidationError
from typing_extensions import (
    Any,
    Iterable,
    Mapping,
    Optional,
    Type,
)

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

from ..context import ProcessingContext
from ..schemas import InputValueError, JsonValue
from .base import (
    InputParameter as InputParameterBase,
)
from .base import ParameterDefinition
from .datetime import ParameterDateTime
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


InputParameterDef = InputParameterBase


#
# Parameter proxy class
#
class _InputParameter:

    @classmethod
    def get(cls, param: ParameterDefinition) -> Type[InputParameterDef]:
        Input = QGIS_TYPES.get(param.type())
        if Input is None:
            raise ValueError(f"Unsupported input parameter: {param}")
        return Input

    def __call__(
        self,
        param: ParameterDefinition,
        project: Optional[QgsProject] = None,
        *,
        validation_only: bool = False,
    ) -> InputParameterDef:
        return self.get(param)(
            param,
            project,
            validation_only=validation_only,
        )

    @staticmethod
    def parameters(
        inputs: Iterable[InputParameterDef],
        params: Mapping[str, JsonValue],
        context: ProcessingContext,
    ) -> Mapping[str, Any]:
        """  Convert inputs to parameters
        """
        def _value(inp: InputParameterDef) -> Any:  # noqa ANN401
            v = params.get(inp.name)
            if not (v or inp.optional):
                raise InputValueError(f"Missing parameter {inp.name}")
            try:
                return inp.value(v, context)
            except ValidationError as e:
                raise InputValueError(f"{inp.name}: Validation error", e) from None

        return {i.name: _value(i) for i in inputs}


InputParameter = _InputParameter()
