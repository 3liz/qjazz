"""Test file destination parsing"""

from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterFileDestination,
)


class TestFileDestination(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testfiledestination"

    def displayName(self) -> str:
        return "Test input file destination"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        param = QgsProcessingParameterFileDestination(
            self.OUTPUT,
            "JSON file",
            fileFilter="JSON files (*.json);; TEXT files (*.text)",
        )
        self.addParameter(param)

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        value = parameters[self.OUTPUT]

        # Create the output file
        with open(value, "w") as fp:
            fp.write('{ "title": "hello json" }')

        return {self.OUTPUT: value}
