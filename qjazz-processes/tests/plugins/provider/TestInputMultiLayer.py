"""Test just returning simple value"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterMultipleLayers,
)


class TestInputMultiLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testinputmultilayer"

    def displayName(self) -> str:
        return "Test Input Multi Layer"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        param = QgsProcessingParameterMultipleLayers(self.INPUT, "Multiple Layer")
        param.setMinimumNumberInputs(1)

        self.addParameter(param)

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """

        # layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)

        return {}
