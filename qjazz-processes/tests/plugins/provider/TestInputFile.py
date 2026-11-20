"""Test just returning simple value"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputString,
    QgsProcessingParameterFile,
)


class TestInputFile(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testinputfile"

    def displayName(self) -> str:
        return "Test Input File"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        param = QgsProcessingParameterFile(
            self.INPUT,
            "Input file",
            extension=".txt",
        )
        self.addParameter(param)
        self.addOutput(QgsProcessingOutputString(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        fileinput = self.parameterAsFile(parameters, self.INPUT, context)
        if feedback:
            feedback.pushInfo("Opening file: %s" % fileinput)

        data = "NO DATA"
        with open(fileinput) as f:
            data = f.read()

        return {self.OUTPUT: data}
