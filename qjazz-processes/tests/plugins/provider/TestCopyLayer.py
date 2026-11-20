"""Test just returning simple value"""

from pathlib import Path
from typing import Any, Optional

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
    QgsVectorFileWriter,
)


class TestCopyLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testcopylayer"

    def displayName(self) -> str:
        return "Test Copy Layer"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, "Vector Layer"))
        self.addParameter(
            QgsProcessingParameterVectorDestination(self.OUTPUT, "Output Layer"),
        )

    def flags(self) -> Qgis.ProcessingAlgorithmFlags:
        return super().flags() | Qgis.ProcessingAlgorithmFlag.RequiresProject

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
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

        if err != QgsVectorFileWriter.WriterError.NoError and feedback:
            feedback.reportError(f"Error  writing vector layer '{outlayer}': {msg}")

        return {self.OUTPUT: outfile}
