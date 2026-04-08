"""Test just returning simple value"""

from typing import Any

from qgis.core import (
    QgsFeedback,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingOutputNumber,
)


class TestUltimateQuestion(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()

    def name(self):
        return "ultimate_question"

    def displayName(self):
        return "Return answer to ultimate question"

    def createInstance(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addOutput(QgsProcessingOutputNumber(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsFeedback,
    ) -> dict:
        return {self.OUTPUT: 42}
