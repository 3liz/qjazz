"""Test just returning simple value"""

from time import sleep
from typing import Any, Optional

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputString,
    QgsProcessingParameterNumber,
)


class TestLongProcess(QgsProcessingAlgorithm):
    DELAY = "DELAY"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testlongprocess"

    def displayName(self) -> str:
        return "Test long time process"

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
                self.DELAY,
                "Delay",
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
        delay = self.parameterAsInt(parameters, self.DELAY, context)

        for i in range(1, 11):
            sleep(delay)
            if feedback:
                feedback.setProgress(i * 10)

        return {self.OUTPUT: f"Slept {delay * 10} seconds"}
