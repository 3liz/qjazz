"""Test just returning simple value"""

from time import sleep

from qgis.core import QgsProcessingAlgorithm, QgsProcessingOutputString, QgsProcessingParameterNumber


class TestLongProcess(QgsProcessingAlgorithm):
    DELAY = "DELAY"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()

    def name(self):
        return "testlongprocess"

    def displayName(self):
        return "Test long time process"

    def createInstance(self, config={}):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(
            QgsProcessingParameterNumber(
                self.DELAY,
                "Delay",
                type=QgsProcessingParameterNumber.Integer,
                minValue=0,
                maxValue=999,
                defaultValue=10,
            )
        )
        self.addOutput(QgsProcessingOutputString(self.OUTPUT, "Output"))

    def processAlgorithm(self, parameters, context, feedback):
        delay = self.parameterAsInt(parameters, self.DELAY, context)

        for i in range(1, 11):
            sleep(delay)
            feedback.setProgress(i * 10)

        return {self.OUTPUT: f"Slept {delay * 10} seconds"}
