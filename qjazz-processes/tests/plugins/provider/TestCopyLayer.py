"""Test just returning simple value"""

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
    QgsVectorFileWriter,
)


class TestCopyLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def __init__(self):
        super().__init__()

    def name(self):
        return "testcopylayer"

    def displayName(self):
        return "Test Copy Layer"

    def createInstance(self, config={}):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config=None):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, "Vector Layer"))
        self.addParameter(
            QgsProcessingParameterVectorDestination(self.OUTPUT, "Output Layer"),
        )

    def flags(self):
        return super().flags() | QgsProcessingAlgorithm.FlagRequiresProject

    def processAlgorithm(self, parameters, context, feedback):
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        outlayer = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        # Get driver from extension
        ext = Path(outlayer).suffix

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = QgsVectorFileWriter.driverForExtension(ext)

        # Save a copy of our layer
        (err, msg, outfile, _layer_name) = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            outlayer,
            context.transformContext(),
            options,
        )

        if err != QgsVectorFileWriter.NoError:
            feedback.reportError(f"Error  writing vector layer '{outlayer}': {msg}")

        return {self.OUTPUT: outfile}
