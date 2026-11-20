from typing import Any

from qgis.core import QgsProcessingAlgorithm, QgsProcessingContext, QgsProcessingFeedback, QgsWkbTypes
from qgis.processing import alg


@alg(name="testinputgeometry", label="test geometry", group="test", group_label="Test scripts")
@alg.output(type=str, name="OUTPUT", label="Output text")
@alg.input(
    type=alg.GEOMETRY,
    name="INPUT",
    label="Vector point",
    # NOTE: Not correctly typed
    geometryTypes=[QgsWkbTypes.GeometryType.Point],  # type: ignore [attr-defined]
    help="multipoint",
    allowMultipart=True,
)
def testgeom(
    instance: QgsProcessingAlgorithm,
    parameters: dict[str, Any],
    context: QgsProcessingContext,
    feedback: QgsProcessingFeedback,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """
    This is a test function that does stuff
    """
    geom = instance.parameterAsGeometry(parameters, "INPUT", context)
    if geom.isEmpty():
        out = "{}"
    else:
        out = geom.asJson()

    return {
        "OUTPUT": out,
    }
