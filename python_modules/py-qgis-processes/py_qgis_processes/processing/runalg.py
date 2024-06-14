#
# Run processing algorithm

import traceback

from pathlib import Path

from typing_extensions import (
    Any,
    Mapping,
    Optional,
)

from qgis.core import (
    QgsMapLayer,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterDefinition,
    QgsProcessingUtils,
    QgsProject,
    QgsWkbTypes,
)

from py_qgis_contrib.core import logger

from .schemas import RunProcessingException


def validate_parameters(
    alg: QgsProcessingAlgorithm,
    parameters: Mapping[str, QgsProcessingParameterDefinition],
    feedback: QgsProcessingFeedback,
    context: QgsProcessingContext,
    abort_on_error: bool = False,
) -> bool:

    # Check parameters value
    ok, msg = alg.checkParameterValues(parameters, context)
    if not ok:
        msg = f"Processing parameters error:\n{msg}"
        feedback.reportError(msg)
        if abort_on_error:
            raise RunProcessingException(msg)
        else:
            return False

    # Validate CRS
    if not alg.validateInputCrs(parameters, context):
        feedback.pushInfo(
            "Warning: not all input layers use the same CRS\n",
            "This can cause unexpected results",
        )

    return True


def execute(
    alg: QgsProcessingAlgorithm,
    parameters: Mapping[str, QgsProcessingParameterDefinition],
    feedback: QgsProcessingFeedback,
    context: QgsProcessingContext,
) -> Mapping[str, Any]:

    """ Re-implementation of `Processing.runAlgorithm`

        see https://github.com/qgis/QGIS/blob/master/python/plugins/processing/core/Processing.py
    """
    validate_parameters(alg, parameters, feedback, context, abort_on_error=True)

    # XXX Fix destination names for models
    # Collect destination names for destination parameters for restoring
    # them later
    destinations = {p: v.destinationName for p, v in parameters.items(
    ) if isinstance(v, QgsProcessingOutputLayerDefinition)}

    # Execute algorithm
    try:
        results, ok = alg.run(parameters, context, feedback, catchExceptions=False)
        if not ok:
            logger.error(f"Algorithm {alg.id()} returned ok={ok}")
    except QgsProcessingException as err:
        # Note: QgsProcessingException exception add stack trace in its message
        raise RunProcessingException(f"Algorithm failed with error {err}") from None
    except Exception as err:
        logger.error(traceback.format_exc())
        raise RunProcessingException(f"Algorithm failed with error {err}") from None

    # From https://github.com/qgis/QGIS/blob/master/python/plugins/processing/core/Processing.py
    for outdef in alg.outputDefinitions():
        output_name = outdef.name()

        if output_name not in destinations:
            continue

        value = results[output_name]
        #
        # Replace the Load On Completion Details name by the original input so
        # that we ensure that layer names will be correct - This is needed
        # for models as they enforce destination name to the output name
        #
        if context.willLoadLayerOnCompletion(value):
            context.layerToLoadOnCompletionDetails(value).name = destinations[output_name]

    return results

#
#  Post processing
#


def process_layer_outputs(
    alg: QgsProcessingAlgorithm,
    context: QgsProcessingContext,
    feedback: QgsProcessingFeedback,
    workdir: Path,
    destination_project: Optional[QgsProject] = None,
) -> bool:
    """ Handle algorithms result layers

        Insert result layers into destination project
    """
    # Transfer layers ownership to destination project
    wrongLayers = []
    for lyrname, details in context.layersToLoadOnCompletion().items():
        try:
            # Take as layer
            layer = QgsProcessingUtils.mapLayerFromString(lyrname, context, typeHint=details.layerTypeHint)

            if layer is None:
                logger.warning("No layer found for %s", lyrname)
                continue

            # Fix layer name
            # Because if details name is empty it well be set to the file name
            # see https://qgis.org/api/qgsprocessingcontext_8cpp_source.html#l00128
            # XXX Make sure that Processing/Configuration/PREFER_FILENAME_AS_LAYER_NAME
            # setting is set to false (see processfactory.py:129)
            details.setOutputLayerName(layer)
            logger.debug("Layer name set to %s <details name was: %s>", layer.name(), details.name)

            # If project is not defined, set the default destination
            # project
            if not details.project and destination_project:
                details.project = destination_project

            # Seek style for layer
            set_output_layer_style(alg, lyrname, layer, details, context, workdir)

            # Add layer to destination project
            if details.project:
                logger.debug(
                    "Adding Map layer '%s' (output_name %s) to Qgs Project",
                    lyrname,
                    details.outputName,
                )
                details.project.addMapLayer(context.temporaryLayerStore().takeMapLayer(layer))

            # Handle post processing
            if details.postProcessor():
                details.postProcessor().postProcessLayer(layer, context, feedback)
        except Exception:
            logger.error(f"Processing: Error loading result layer:\n{traceback.format_exc()}")
            wrongLayers.append(str(lyrname))

    if wrongLayers:
        wronglist = '\n'.join(str(lay) for lay in wrongLayers)
        logger.error(
            "The following layers were not correctly generated:\n%s"
            "You can check the log messages to find more information "
            "about the execution of the algorithm",
            wronglist,
        )

    return len(wrongLayers) == 0


def set_output_layer_style(
    alg: QgsProcessingAlgorithm,
    layerName: str,
    layer: QgsMapLayer,
    details: QgsProcessingContext.LayerDetails,
    context: QgsProcessingContext,
    workdir: Path,
):
    """ Set layer style

        Original code is from python/plugins/processing/gui/Postprocessing.py
    """
    # XXX processing is accesible only after qgis initialization
    from processing.core.Processing import ProcessingConfig as QgisProcessingConfig
    from processing.core.Processing import RenderingStyles

    output_name = details.outputName

    style = None
    if output_name:
        # If a style with the same name as the output name exists
        # in workdir then use it
        style = workdir.joinpath(f"{output_name}.qml")
        if not style.is_file():
            # Fallback to defined rendering styles
            style = RenderingStyles.getStyle(alg.id(), output_name)
        logger.trace("Getting style for %s: %s <%s>", alg.id(), output_name, style)

    # Get defaults styles
    if style is None:
        # Load default styles
        layer.loadDefaultStyle()

        if layer.type() == QgsMapLayer.RasterLayer:
            style = QgisProcessingConfig.getSetting(QgisProcessingConfig.RASTER_STYLE)
        else:
            if layer.geometryType() == QgsWkbTypes.PointGeometry:
                style = QgisProcessingConfig.getSetting(QgisProcessingConfig.VECTOR_POINT_STYLE)
            elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                style = QgisProcessingConfig.getSetting(QgisProcessingConfig.VECTOR_LINE_STYLE)
            else:
                style = QgisProcessingConfig.getSetting(QgisProcessingConfig.VECTOR_POLYGON_STYLE)
    if style:
        logger.trace("Adding style '%s' to layer %s (output_name %s)", style, details.name, output_name)
        layer.loadNamedStyle(style)
