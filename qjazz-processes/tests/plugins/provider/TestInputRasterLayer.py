"""Test just returning simple value"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterRasterLayer,
)


class TestInputRasterLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testinputrasterlayer"

    def displayName(self) -> str:
        return "Test Input Raster Layer"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Raster Layer"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        _layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)

        return {}
