from types import MappingProxyType

from typing_extensions import Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingOutputBoolean,
    QgsProcessingOutputConditionalBranch,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputHtml,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputNumber,
    QgsProcessingOutputPointCloudLayer,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputString,
    QgsProcessingOutputVariant,
    QgsProcessingOutputVectorLayer,
    QgsProcessingOutputVectorTileLayer,
)

from .base import OutputDefinition
from .base import OutputParameter as OutputParameterBase
from .files import (
    OutputFile,
    OutputFolder,
    OutputHtml,
)
from .layers import (
    OutputMapLayer,
    OutputMultipleLayers,
    OutputPointCloudLayer,
    OutputRasterLayer,
    OutputVectorLayer,
    OutputVectorTileLayer,
)
from .literals import (
    OutputBoolean,
    OutputNumber,
    OutputString,
)

# Type mapping

QGIS_TYPES = MappingProxyType({
    QgsProcessingOutputBoolean.typeName(): OutputBoolean,
    QgsProcessingOutputConditionalBranch.typeName(): None,
    QgsProcessingOutputFile.typeName(): OutputFile,
    QgsProcessingOutputFolder.typeName(): OutputFolder,
    QgsProcessingOutputHtml.typeName(): OutputHtml,
    QgsProcessingOutputMapLayer.typeName(): OutputMapLayer,
    QgsProcessingOutputMultipleLayers.typeName(): OutputMultipleLayers,
    QgsProcessingOutputNumber.typeName(): OutputNumber,
    QgsProcessingOutputPointCloudLayer.typeName(): OutputPointCloudLayer,
    QgsProcessingOutputRasterLayer.typeName(): OutputRasterLayer,
    QgsProcessingOutputString.typeName(): OutputString,
    QgsProcessingOutputVariant.typeName(): None,
    QgsProcessingOutputVectorLayer.typeName(): OutputVectorLayer,
    QgsProcessingOutputVectorTileLayer.typeName(): OutputVectorTileLayer,
})


OutputParameterDef = OutputParameterBase


def OutputParameter(
    out: OutputDefinition,
    alg: Optional[QgsProcessingAlgorithm] = None,
) -> OutputParameterDef:

    Output = QGIS_TYPES.get(out.type())
    if Output is None:
        raise ValueError(f"Unsupported output parameter: {out}")

    return Output(out, alg)
