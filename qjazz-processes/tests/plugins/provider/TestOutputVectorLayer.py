"""Returns a simple bar chart"""

import traceback

from pathlib import Path
from typing import Any, Optional

import processing

from qgis.core import (
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
)


class TestOutputVectorLayer(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    DISTANCE = "DISTANCE"
    OUTPUT = "OUTPUT"

    def __init__(self) -> None:
        super().__init__()

    def name(self) -> str:
        return "vectoroutput"

    def displayName(self) -> str:
        return "Vector output test"

    def createInstance(self, config: Optional[dict[str, Any]] = None) -> QgsProcessingAlgorithm:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None) -> None:
        """Virtual override

        see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT,
                "Input layer",
            ),
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.DISTANCE, "Distance", type=Qgis.ProcessingNumberParameterType.Double, defaultValue=1000
            )
        )

        self.addOutput(QgsProcessingOutputVectorLayer(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        try:
            output = str(Path(context.temporaryFolder()).joinpath("my_output_vector.fgb"))

            # Run buffer
            _buffer_result = processing.run(
                "qgis:buffer",
                {
                    "INPUT": parameters[self.INPUT],
                    "DISTANCE": parameters[self.DISTANCE],
                    "SEGMENTS": 10,
                    "END_CAP_STYLE": 0,
                    "JOIN_STYLE": 0,
                    "MITER_LIMIT": 2,
                    "DISSOLVE": False,
                    "OUTPUT": output,
                },
                context=context,
                feedback=feedback,
            )

            return {self.OUTPUT: output}

        except Exception:
            traceback.print_exc()
            raise
