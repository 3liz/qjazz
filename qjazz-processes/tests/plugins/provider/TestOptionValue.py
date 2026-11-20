"""Test just returning simple value"""

from typing import Any, ClassVar, Optional

from qgis.core import (
    QgsApplication,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputString,
    QgsProcessingParameterEnum,
)


class TestOptionValue(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    IN_OPTIONS: ClassVar = ["value1", "value2", "value3"]

    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def tr(string: str, context: str = "") -> str:
        return QgsApplication.translate(context or "Processing", string)

    def name(self) -> str:
        return "testoptionvalue"

    def displayName(self) -> str:
        return "Test Option Value"

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
            QgsProcessingParameterEnum(
                self.INPUT,
                "Values",
                optional=True,
                defaultValue=1,
                options=self.IN_OPTIONS,
            ),
        )
        self.addOutput(QgsProcessingOutputString(self.OUTPUT, "Output"))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: Optional[QgsProcessingFeedback],
    ) -> dict[str, Any]:
        param = self.parameterAsString(parameters, self.INPUT, context)

        return {self.OUTPUT: "selection is %s" % (param)}
