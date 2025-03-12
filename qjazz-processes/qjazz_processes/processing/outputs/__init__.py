from types import MappingProxyType
from typing import Optional

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


class UnsupportedOutput(OutputParameterBase):
    #
    # Mark unsupported output parameters as hidden parameters
    #
    # Those paramaters are still valid parameters but makes no sense
    # when used in the context of a processes api.
    #

    def initialize(self):
        raise NotImplementedError(f"{self._param} cannot be instancied")

    @classmethod
    def hidden(cls, outp: OutputDefinition) -> bool:
        return True


# Type mapping

OutputTypes = MappingProxyType({
    QgsProcessingOutputBoolean.typeName(): OutputBoolean,
    QgsProcessingOutputConditionalBranch.typeName(): UnsupportedOutput,
    QgsProcessingOutputFile.typeName(): OutputFile,
    QgsProcessingOutputFolder.typeName(): OutputFolder,
    QgsProcessingOutputHtml.typeName(): OutputHtml,
    QgsProcessingOutputMapLayer.typeName(): OutputMapLayer,
    QgsProcessingOutputMultipleLayers.typeName(): OutputMultipleLayers,
    QgsProcessingOutputNumber.typeName(): OutputNumber,
    QgsProcessingOutputPointCloudLayer.typeName(): OutputPointCloudLayer,
    QgsProcessingOutputRasterLayer.typeName(): OutputRasterLayer,
    QgsProcessingOutputString.typeName(): OutputString,
    QgsProcessingOutputVariant.typeName(): UnsupportedOutput,
    QgsProcessingOutputVectorLayer.typeName(): OutputVectorLayer,
    QgsProcessingOutputVectorTileLayer.typeName(): OutputVectorTileLayer,
})


OutputParameterDef = OutputParameterBase


#
# Parameter proxy class
#
class _OutputParameter:

    @classmethod
    def get(cls, out: OutputDefinition) -> type[OutputParameterDef]:
        Output = OutputTypes.get(out.type())
        if Output is None:
            raise ValueError(f"Unsupported input parameter: {out}")
        return Output

    def __call__(
        self,
        out: OutputDefinition,
        alg: Optional[QgsProcessingAlgorithm] = None,
    ) -> OutputParameterDef:
        return self.get(out)(out, alg)


OutputParameter = _OutputParameter()
