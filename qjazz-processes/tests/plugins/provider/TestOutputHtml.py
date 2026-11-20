"""Test html output"""

from pathlib import Path
from typing import Any, Optional

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputHtml,
)


class TestOutputHtml(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testoutputhtml"

    def displayName(self) -> str:
        return "Test output html"

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
            QgsProcessingOutputHtml(
                self.OUTPUT,
                "HTML report",
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        value = "report.html"

        # Create the output file
        with Path(value).open("w") as fp:
            fp.write("<html><body><h1>hello html</h1></body></html>")

        return {self.OUTPUT: value}
