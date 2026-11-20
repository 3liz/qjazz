"""Test just returning simple value"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputNumber,
)


class TestUltimateQuestion(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "ultimate_question"

    def displayName(self) -> str:
        return "Return answer to ultimate question"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addOutput(QgsProcessingOutputNumber(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        return {self.OUTPUT: 42}
