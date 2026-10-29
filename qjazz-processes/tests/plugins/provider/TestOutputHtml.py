"""Test html output"""

from pathlib import Path

from qgis.core import QgsProcessingAlgorithm, QgsProcessingOutputHtml


class TestOutputHtml(QgsProcessingAlgorithm):
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()

    def name(self):
        return "testoutputhtml"

    def displayName(self):
        return "Test output html"

    def createInstance(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addOutput(
            QgsProcessingOutputHtml(
                self.OUTPUT,
                "HTML report",
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        value = "report.html"

        # Create the output file
        with Path(value).open("w") as fp:
            fp.write("<html><body><h1>hello html</h1></body></html>")

        return {self.OUTPUT: value}
