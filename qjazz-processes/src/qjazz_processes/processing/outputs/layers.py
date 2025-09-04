# mypy: disable-error-code="has-type"
# Note: mypy cannot resolve multiple inherited property decorated
# methods
#
#  Layers outputs
#
import traceback

from pathlib import Path
from typing import (
    ClassVar,
    Sequence,
    TypeAlias,
)
from urllib.parse import quote, urlencode

from qgis.core import (
    Qgis,
    QgsMapLayer,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingUtils,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_postcondition
from qjazz_processes.schemas import (
    Format,
    Formats,
    JsonDict,
    Link,
    OutputFormat,
    OutputFormatDefinition,
    ValuePassing,
    mimetypes,
)

from .base import (
    JsonValue,
    OutputDefinition,
    OutputParameter,
    ProcessingContext,
)

LayerHint: TypeAlias = QgsProcessingUtils.LayerHint


class OutputLayerBase(OutputParameter, OutputFormatDefinition):  # type: ignore [misc]
    _Model = Link

    _ServiceFormats: ClassVar[Sequence[Format]] = ()
    _LayerHint: ClassVar[LayerHint] = LayerHint.UnknownType

    def initialize(self):
        if self._ServiceFormats:
            self.output_format = OutputFormat(media_type=self._ServiceFormats[0].media_type)

    def value_passing(self) -> ValuePassing:
        return ("byReference",)

    def json_schema(self) -> JsonDict:
        schema = super().json_schema()

        formats = self.allowed_formats
        if formats:
            schema = {
                "$defs": {"Link": schema},
                "oneOf": [
                    {
                        "$ref": "#/$defs/Link",
                        "contentMediaType": fmt.media_type,
                        "title": fmt.title,
                    }
                    for fmt in formats
                ],
            }

        return schema

    @classmethod
    def get_output_formats(
        cls,
        outdef: OutputDefinition,
        alg: QgsProcessingAlgorithm,
    ) -> Sequence[Format]:
        return cls._ServiceFormats

    def output(
        self,
        value: str,
        context: ProcessingContext,
    ) -> JsonValue:
        layer, name = add_layer_to_load_on_completion(
            value,
            self.name,
            context,
            self._LayerHint,
        )

        self.advertise_layer(layer, name, context)

        media_type = self.output_format.media_type

        reference_url = context.ows_reference(
            service=Format.service(media_type),
            version=Format.version(media_type),
            query=urlencode((("LAYERS", name),), quote_via=quote),
        )

        return Link(
            href=reference_url,
            mime_type=media_type,
            title=self.title,
            description=self._out.description(),
        ).model_dump(mode="json", by_alias=True, exclude_none=True)

    def advertise_layer(self, layer: QgsMapLayer, name: str, context: ProcessingContext):
        """Advertised layer for server GetCapabilities requests"""
        datasource = Path(layer.source())

        if datasource.exists() and datasource.is_relative_to(context.workdir):
            media_type = mimetypes.types_map.get(datasource.suffix, Formats.ANY.media_type)
            if Qgis.QGIS_VERSION_INT >= 33800:
                props = layer.serverProperties()
                props.setDataUrl(context.file_reference(datasource))
                props.setDataUrlFormat(media_type)
            else:
                layer.setDataUrl(context.file_reference(datasource))
                layer.setDataUrlFormat(media_type)


#
# QgsProcessingOutputMapLayer
#


class OutputMapLayer(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
    )


#
# QgsProcessingOutputRasterLayer
#


class OutputRasterLayer(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
        Formats.WCS,
        Formats.WCS100,
        Formats.WCS110,
    )

    _LayerHint = LayerHint.Raster


#
# QgsProcessingOutputVectorLayer
#


class OutputVectorLayer(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
        Formats.WFS,
        Formats.WFS100,
        Formats.WFS110,
    )

    _LayerHint = LayerHint.Vector


#
# QgsProcessingOutputVectorTileLayer
#


class OutputVectorTileLayer(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
    )

    _LayerHint = LayerHint.VectorTile


#
# QgsProcessingOutputPointCloudLayer
#


class OutputPointCloudLayer(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
    )

    _LayerHint = LayerHint.PointCloud


#
# QgsProcessingOutputMultipleLayers
#


class OutputMultipleLayers(OutputLayerBase):
    _ServiceFormats = (
        Formats.WMS,
        Formats.WMS111,
        Formats.WMS130,
        Formats.WMTS,
        Formats.WMTS100,
    )

    def output(
        self,
        value: Sequence[str],
        context: ProcessingContext,
    ) -> JsonValue:
        layers = ",".join(
            layer.name
            for layer, name in (
                add_layer_details(
                    self.name,
                    v,
                    self._LayerHint,
                    context,
                )
                for v in value
            )
        )

        media_type = self.output_format.media_type
        reference_url = context.ows_reference(
            service=Format.service(media_type),
            query=urlencode((("LAYERS", layers),), quote_via=quote),
        )

        return Link(
            href=reference_url,
            mime_type=media_type,
            title=self.title,
            description=self._out.description(),
        ).model_dump(mode="json", by_alias=True, exclude_none=True)


#
#  Utils
#


def add_layer_to_load_on_completion(
    value: str,
    output_name: str,
    context: QgsProcessingContext,
    hint: LayerHint,
) -> QgsMapLayer:
    """Add layer to load on completion
    The layer will be added to the destination project

    Return the name of the layer
    """
    if context.willLoadLayerOnCompletion(value):
        # Do not add the layer twice: may be already added
        # in layer destination parameter
        try:
            details = context.layerToLoadOnCompletionDetails(value)
            layer = QgsProcessingUtils.mapLayerFromString(
                value,
                context,
                typeHint=details.layerTypeHint,
            )
            assert_postcondition(layer is not None, f"No layer found for '{value}'")
            if details.name:
                logger.debug(
                    "Skipping already added layer for %s (details name: %s)",
                    output_name,
                    details.name,
                )
                name = details.name
            else:
                details.setOutputLayerName(layer)
                name = layer.name()
                logger.debug("Layer name for '%s' set to '%s'", output_name, name)
        except Exception:
            logger.error(
                "Processing: Error loading result layer for  %s:\n%s",
                value,
                traceback.format_exc(),
            )
            raise

        return layer, name
    else:
        return add_layer_details(output_name, value, hint, context)


def add_layer_details(
    output_name: str,
    value: str,
    hint: LayerHint,
    context: QgsProcessingContext,
) -> tuple[QgsMapLayer, str]:
    #
    # Create new layer details and call addLayerToLoadOnCompletion
    #

    # Set empty name as we are calling setOutputLayerName
    details = QgsProcessingContext.LayerDetails("", context.destination_project, output_name, hint)
    try:
        layer = QgsProcessingUtils.mapLayerFromString(
            value,
            context,
            typeHint=details.layerTypeHint,
        )
        assert_postcondition(layer is not None, f"No layer found for '{value}'")
        # Fix layer name
        # Because if details name is empty it will be set to the file name
        # see https://qgis.org/api/qgsprocessingcontext_8cpp_source.html#l00128
        # XXX Make sure that Processing/Configuration/PREFER_FILENAME_AS_LAYER_NAME
        # setting is set to false (see processfactory.py:129)
        details.setOutputLayerName(layer)
        logger.debug("Layer name for '%s' set to '%s'", output_name, layer.name())
        context.addLayerToLoadOnCompletion(value, details)
    except Exception:
        logger.error(
            "Processing: Error loading result layer %s:\n%s",
            value,
            traceback.format_exc(),
        )
        raise

    return layer, layer.name()
