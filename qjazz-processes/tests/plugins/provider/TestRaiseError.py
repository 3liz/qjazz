"""Test just returning simple value"""

from typing import Any, Optional

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputString,
    QgsProcessingParameterNumber,
)


class TestRaiseError(QgsProcessingAlgorithm):
    PARAM1 = "PARAM1"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testraiseerror"

    def displayName(self) -> str:
        return "Test raising error"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PARAM1,
                "Parameter 1",
                type=Qgis.ProcessingNumberParameterType.Integer,
                minValue=0,
                maxValue=999,
                defaultValue=10,
            )
        )
        self.addOutput(QgsProcessingOutputString(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        param1 = self.parameterAsInt(parameters, self.PARAM1, context)

        raise Exception("I'm melting !!!")

        return {self.OUTPUT: "%s" % param1}
