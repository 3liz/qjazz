# mypy: disable-error-code="has-type"
# Note: mypy cannot resolve multiple inherited property decorated
# methods
#
#  Layers outputs
#
import traceback

from pydantic import TypeAdapter
from typing_extensions import (
    Any,
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    TypeAlias,
)

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingUtils,
)

from py_qgis_contrib.core import logger
from py_qgis_processes_schemas import (
    Format,
    Formats,
    Link,
    NullField,
    OutputFormat,
    OutputFormatDefinition,
    ValuePassing,
)

from .base import (
    JsonValue,
    Metadata,
    MetadataValue,
    OutputDefinition,
    OutputParameter,
    ProcessingContext,
)

LayerHint: TypeAlias = QgsProcessingUtils.LayerHint


class OutputLayerBase(OutputParameter, OutputFormatDefinition):  # type: ignore [misc]

    _ServiceFormats: ClassVar[Sequence[Format]] = ()
    _LayerHint: ClassVar[LayerHint] = LayerHint.UnknownType

    def initialize(self):
        if self._ServiceFormats:
            self.output_format = OutputFormat(media_type=self._ServiceFormats[0].media_type)

    def value_passing(self) -> ValuePassing:
        return ('byReference',)

    @classmethod
    def metadata(cls, outdef: OutputDefinition) -> List[Metadata]:
        md = super(OutputLayerBase, cls).metadata(outdef)
        md.append(
            MetadataValue(
                role="allowedFormats",
                value=[
                    {
                        "media_type": f.media_type,
                        'title': f.title,
                    }
                    for f in cls._ServiceFormats
                ],
            ),
        )
        return md

    @classmethod
    def create_model(
        cls,
        outp: OutputDefinition,
        field: Dict,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> TypeAlias:

        _type: Any = Link

        formats = cls.get_output_formats(outp, alg)
        if formats:
            class _Ref(_type):
                mime_type: Optional[         # type: ignore [valid-type]
                    Literal[tuple(fmt.media_type for fmt in formats)]
                ] = NullField(serialization_alias="type")

            _type = _Ref

        return _type

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

        name = add_layer_to_load_on_completion(
            value,
            self.name,
            context,
            self._LayerHint,
        )

        media_type = self.output_format.media_type

        reference_url = context.ows_reference(name, service=Format.service(media_type))

        return Link(
            href=reference_url,
            mime_type=media_type,
            title=self.title,
            description=self._out.description,
        ).model_dump(mode='json', by_alias=True, exclude_none=True)


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

    @classmethod
    def create_model(
        cls,
        outp: OutputDefinition,
        field: Dict,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> TypeAlias:

        _type: Any = super(OutputMultipleLayers, cls).create_model(outp, field, alg)
        return Sequence[_type]

    def output(
        self,
        value: Sequence[str],
        context: ProcessingContext,
    ) -> JsonValue:

        media_type = self.output_format.media_type
        service = Format.service(media_type)

        links = [
            Link(
                href=context.ows_reference(name, service=service),
                media_type=media_type,
            ) for name in (
                add_layer_details(
                    self.name,
                    lyrname,
                    self._LayerHint,
                    context,
                ) for lyrname in value
            )
        ]

        return TypeAdapter(self.model).dump_python(
            links,
            mode='json',
            by_alias=True,
            exclude_none=True,
        )


#
#  Utils
#

def add_layer_to_load_on_completion(
    value: str,
    output_name: str,
    context: QgsProcessingContext,
    hint: LayerHint,
) -> str:
    """ Add layer to load on completion
        The layer will be added to the destination project

        Return the name of the layer
    """
    if context.willLoadLayerOnCompletion(value):
        # Do not add the layer twice: may be already added
        # in layer destination parameter
        details = context.layerToLoadOnCompletionDetails(value)
        if details.name:
            logger.debug(
                "Skipping already added layer for %s (details name: %s)",
                output_name,
                details.name,
            )
            layer_name = details.name
        else:
            try:
                layer = QgsProcessingUtils.mapLayerFromString(
                    value,
                    context,
                    typeHint=details.layerTypeHint,
                )
                if layer is not None:
                    details.setOutputLayerName(layer)
                    logger.debug("Layer name for '%s' set to '%s'", output_name, layer.name())
                    layer_name = layer.name()
            except Exception:
                logger.error(
                    "Processing: Error loading result layer %s:\n%s",
                    layer.name(),
                    traceback.format_exc(),
                )
                raise
        return layer_name
    else:
        return add_layer_details(output_name, value, hint, context)


def add_layer_details(
    output_name: str,
    lyrname: str,
    hint: LayerHint,
    context: QgsProcessingContext,
) -> str:
    #
    # Create new layer details and call addLayerToLoadOnCompletion
    #

    # Set empty name as we are calling setOutputLayerName
    details = QgsProcessingContext.LayerDetails("", context.destination_project, output_name, hint)
    try:
        layer = QgsProcessingUtils.mapLayerFromString(
            lyrname,
            context,
            typeHint=details.layerTypeHint,
        )
        if layer is None:
            raise ValueError("No layer found for '%s'", lyrname)
        # Fix layer name
        # Because if details name is empty it will be set to the file name
        # see https://qgis.org/api/qgsprocessingcontext_8cpp_source.html#l00128
        # XXX Make sure that Processing/Configuration/PREFER_FILENAME_AS_LAYER_NAME
        # setting is set to false (see processfactory.py:129)
        details.setOutputLayerName(layer)
        logger.debug("Layer name for '%s' set to '%s'", output_name, layer.name())
        context.addLayerToLoadOnCompletion(lyrname, details)
        result = layer.name()
    except Exception:
        logger.error(
            "Processing: Error loading result layer %s:\n%s",
            lyrname,
            traceback.format_exc(),
        )
        raise

    return result
