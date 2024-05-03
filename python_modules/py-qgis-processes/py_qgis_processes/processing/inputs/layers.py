

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from pydantic import BaseModel, Extra, JsonValue
from typing_extensions import (
    Any,
    Dict,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
)

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterLimitedDataTypes,
    QgsProject,
)

from ..utils import (
    ProcessingSourceType,
    get_valid_filename,
    layer_names_from_context,
    parse_layer_spec,
    raw_destination_sink,
)
from .base import InputParameter, ParameterDefinition

#
# Layers input may be passed in various forms:
#
#    - For input layers and if a context is given: it will be a list of available layers from
#      the source project as literal string.
#
#    We treat layer destination the same as input since they refer to
#    layers ids in qgisProject
#


class ParameterMapLayer(InputParameter):

    _DefaultSourceType = ProcessingSourceType.MapLayer
    _multiple: bool = False
    _format: str = "x-qgis-parameter-maplayer"

    @classmethod
    def sourcetypes(cls, param: ParameterDefinition) -> Set[ProcessingSourceType]:  # type: ignore [valid-type]
        if isinstance(param, QgsProcessingParameterLimitedDataTypes):
            return set(param.dataTypes())
        else:
            return {cls._DefaultSourceType}

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        sourcetypes = cls.sourcetypes(param)

        _type: Any = str

        if project:
            allowed_sources = layer_names_from_context(project, sourcetypes)
            if allowed_sources:
                _type = Literal[allowed_sources]

        if cls._multiple:
            _type = Set[_type]

        if not validation_only:
            field['format'] = cls._format

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[QgsProcessingContext] = None,
    ) -> str | Sequence[str]:

        _inp = self.validate(inp)
        if self._multiple:
            _inp = [parse_layer_spec(s)[0] for s in _inp]
        else:
            _inp = parse_layer_spec(_inp)[0]

        return _inp


#
# QgsProcessingParameterMultipleLayers
#

class ParameterMultipleLayers(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _multiple = True
    _format: str = "x-qgis-parameter-multiplelayers"


#
# QgsProcessingParameterVectorLayer
#

class ParameterVectorLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _format = "x-qgis-parameter-vectorlayer"

#
# QgsProcessingParameterFeatureSource
#


class ParameterFeatureSource(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _format = "x-qgis-parameter-featuresource"

    def value(
        self,
        inp: JsonValue,
        context: Optional[QgsProcessingContext] = None,
    ) -> QgsProcessingFeatureSourceDefinition:

        #
        # Support feature selection
        #
        _inp = self.validate(inp)

        value, has_selection = parse_layer_spec(_inp, context, allow_selection=True)
        value = QgsProcessingFeatureSourceDefinition(value, selectedFeaturesOnly=has_selection)

        return value

#
# QgsProcessingParameterRasterLayer
#


class ParameterRasterLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Raster
    _format = "x-qgis-parameter-rasterlayer"


#
# QgsProcessingParameterMeshLayer
#


class ParameterMeshLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Mesh
    _format = "x-qgis-parameter-meshlayer"


#
# QgsProcessingParameterPointCloudLayer
#

class ParameterPointCloudLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.PointCloud
    _format = "x-qgis-parameter-pointcloudlayer"


#
# QgsProcessingParameterVectorTileWriterLayers
#

class ParameterVectorTileWriterLayers(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _multiple = True
    _format = "x-qgis-parameter-vectortilewriterlayers"

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = super(cls, cls).create_model(
            param,
            field,
            project,
            validation_only,
        )

        # Inputs are List of dict
        # Build intermediate representation for
        # enforcing constraints
        class TileWriter(BaseModel, extra=Extra.allow):
            layer: _type

        return Sequence[TileWriter]

    def value(self, inp: JsonValue, context: Optional[QgsProcessingContext] = None) -> str:

        _inp = self.validate(inp)
        return _inp.model_dump(mode='json')


#
# Layer destination
#

class Metadata(SimpleNamespace):
    pass


class ParameterLayerDestination(InputParameter):
    _format: Optional[str] = None

    @classmethod
    def get_default_value(cls, field: Dict, param: ParameterDefinition) -> Tuple[str, str]:
        #
        # Get the file extension as we need it
        # for writing the resulting file
        #
        defval = field.pop('default', None)

        ext = param.defaultFileExtension()

        # XXX Need to be revisited
        if isinstance(defval, QgsProcessingOutputLayerDefinition):
            sink = defval.sink
            if sink:
                # Try to get extension from the sink value
                sink = sink.staticValue()
                if sink:
                    # Remove extra open options
                    url = urlsplit(sink.partition('|')[0])
                    if url.path and url.scheme.lower() in ('', 'file'):
                        p = Path(url.path)
                        ext = p.suffix.removeprefix('.') or ext
                        defval = defval.destinationName or p.stem

        return ext, defval

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type = str

        # Since QgsProcessingOutputLayerDefinition may
        # be defined as default value, get extension
        # and layer name from it

        ext, defval = cls.get_default_value(field, param)

        if not validation_only:
            field.update(default=defval)
            schema_extra = {}
            if cls._format:
                schema_extra['format'] = cls._format
            field.update(json_schema_extra=schema_extra)

        # Add field metadata
        field.update(metadata=Metadata(ext=ext))

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[QgsProcessingContext] = None,
    ) -> QgsProcessingOutputLayerDefinition:

        destination = self.validate(inp)

        extension = self.metadata.ext

        if self.config.raw_destination_input_sink:
            sink, destination = raw_destination_sink(
                self._param,
                destination,
                extension,
                self.config.raw_destination_root_path,
            )
        else:
            #
            # Destination layer: a new layer is created as file with the input name.
            # Do not supports memory layer because we need persistence
            #
            self._param.setSupportsNonFileBasedOutput(False)
            #
            # Enforce pushing created layers to layersToLoadOnCompletion list
            # i.e layer will be stored in the destination project

            output_name = get_valid_filename(self._param.name())
            # Use canonical file name
            sink = f"./{output_name}.{extension}"

        destination_project = context and context.destination_project

        value = QgsProcessingOutputLayerDefinition(sink, destination_project)
        value.destinationName = destination

        return value


#
# QgsProcessingParameterRasterDestination
#

class ParameterRasterDestination(ParameterLayerDestination):
    _format = "x-qgis-parameter-rasterdestination"


#
# QgsProcessingParameterVectorDestination
#

class ParameterVectorDestination(ParameterLayerDestination):
    _format = "x-qgis-parameter-vectordestination"

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type = super(cls, cls).create_model(
            param,
            field,
            project,
            validation_only,
        )

        if not validation_only:
            schema_extra = field.get('json_schema_extra', {})
            schema_extra['x-qgis-datatype'] = str(param.dataType())
            field.update(json_schema_extra=schema_extra)

        return _type


#
# QgsProcessingParameterFeatureSink
#

class ParameterFeatureSink(ParameterVectorDestination):
    _format = "x-qgis-parameter-featuresink"


#
# QgsProcessingPointCloudDestination
#

class ParameterPointCloudDestination(ParameterLayerDestination):
    _format = "x-qgis-parameter-pointclouddestination"

#
# QgsProcessingVectorTileDestination
#


class ParameterVectorTileDestination(ParameterLayerDestination):
    _format = "x-qgis-parameter-vectortiledestination"
