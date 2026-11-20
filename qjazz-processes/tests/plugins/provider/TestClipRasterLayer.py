"""Test just returning simple value"""

from typing import Any, Optional

import processing

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)


class TestClipRasterLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    EXTENT = "EXTENT"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "testcliprasterlayer"

    def displayName(self) -> str:
        return "Test Clip Raster Layer"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, "Raster Layer"))
        self.addParameter(QgsProcessingParameterExtent(self.EXTENT, "Clip Extent"))
        self.addParameter(QgsProcessingParameterRasterDestination(self.OUTPUT, "Clipped Layer"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        output = self.parameterAsOutputLayer(parameters, "OUTPUT", context)

        # Run buffer
        _buffer_result = processing.run(
            "gdal:cliprasterbyextent",
            {
                "INPUT": parameters["INPUT"],
                "PROJWIN": parameters["EXTENT"],
                "NODATA": None,
                "OPTIONS": "",
                "DATA_TYPE": 0,
                "OUTPUT": output,
            },
            context=context,
            feedback=feedback,
        )

        return {self.OUTPUT: output}
