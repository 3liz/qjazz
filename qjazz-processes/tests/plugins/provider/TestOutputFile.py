"""Test file destination parsing"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
)


class TestOutputFile(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testoutputfile"

    def displayName(self) -> str:
        return "Test output file"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addOutput(
            QgsProcessingOutputFile(
                self.OUTPUT,
                "JSON output file",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        value = "output.json"

        # Create the output file
        with open(value, "w") as fp:
            fp.write('{ "title": "hello json" }')

        return {self.OUTPUT: value}
