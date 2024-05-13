
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Extra, Field, JsonValue
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
)

from qgis.core import (
    Qgis,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterBand,
    QgsProcessingParameterExpression,
    QgsProcessingParameterField,
    QgsProcessingParameterFieldMapping,
    QgsProcessingParameterLimitedDataTypes,
    QgsProject,
)

from py_qgis_processes_schemas.models import NullField

from ..utils import (
    ProcessingSourceType,
    get_valid_filename,
    layer_names_from_context,
    parse_layer_spec,
    raw_destination_sink,
)
from .base import (
    InputMeta,
    InputParameter,
    Metadata,
    MetadataValue,
    ParameterDefinition,
    ProcessingContext,
)

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

    @classmethod
    def is_spatial(cls) -> Optional[bool]:
        # Do not care if layer is spatial or not
        return None

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
            allowed_sources = layer_names_from_context(project, sourcetypes, cls.is_spatial())
            if allowed_sources:
                _type = Literal[allowed_sources]

        if cls._multiple:
            _type = Set[_type]

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> JsonValue:

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


#
# QgsProcessingParameterVectorLayer
#

class ParameterVectorLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector

#
# QgsProcessingParameterFeatureSource
#


class ParameterFeatureSource(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
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


#
# QgsProcessingParameterPointCloudLayer
#

class ParameterPointCloudLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.PointCloud


#
# QgsProcessingParameterVectorTileWriterLayers
#

class ParameterVectorTileWriterLayers(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _multiple = True

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

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> Dict:
        _inp = self.validate(inp)
        return self._model.dump_python(_inp, mode='json', by_alias=True, exclude_none=True)


#
# QgsProcessingParameterDxfLayers
#

class ParameterDxfLayers(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _multiple: bool = True

    @classmethod
    def is_spatial(cls) -> Optional[bool]:
        # Require spatial layers
        return True


#
# QgsProcessingParameterAnnotationLayer
#

class ParameterAnnotationLayer(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Annotation


#
# QgsProcessingParameterTinInputLayers
#

class ParameterTinInputLayers(ParameterMapLayer):
    _DefaultSourceType = ProcessingSourceType.Vector
    _multiple = True

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
        class TinInput(BaseModel, extra='allow'):
            source: _type
            attributeIndex: str
            type_: str = Field(alias="type")

        return Sequence[TinInput]

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> Dict:
        _inp = self.validate(inp)
        return self._model.dump_python(_inp, mode='json', by_alias=True, exclude_none=True)

#
# Layer destination
#


class ParameterLayerDestination(InputParameter):

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
            if defval:
                field.update(default=defval)

        # Add field metadata
        field.update(meta=InputMeta(ext=ext))

        return _type

    def value(
        self,
        inp: JsonValue,
        context: Optional[ProcessingContext] = None,
    ) -> QgsProcessingOutputLayerDefinition:

        context = context or ProcessingContext()

        destination = self.validate(inp)

        extension = self.meta.ext

        if context.config.raw_destination_input_sink:
            sink, destination = raw_destination_sink(
                self._param,
                destination,
                extension,
                context.config.raw_destination_root_path,
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
            sink = str(context.workdir.joinpath(f"{output_name}.{extension}"))

        destination_project = context.destination_project

        value = QgsProcessingOutputLayerDefinition(sink, destination_project)
        value.destinationName = destination

        return value


#
# QgsProcessingParameterRasterDestination
#

class ParameterRasterDestination(ParameterLayerDestination):
    pass

#
# QgsProcessingParameterVectorDestination
#


class ParameterVectorDestination(ParameterLayerDestination):

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
    pass


#
# QgsProcessingPointCloudDestination
#

class ParameterPointCloudDestination(ParameterLayerDestination):
    pass


#
# QgsProcessingVectorTileDestination
#

class ParameterVectorTileDestination(ParameterLayerDestination):
    pass


#
# QgsProcessingParameterField
#

if Qgis.QGIS_VERSION_INT >= 33600:
    FieldParameterDataType = Qgis.ProcessingFieldParameterDataType
    def field_datatype_name(value: Qgis.ProcessingFieldParameterDataType) -> str:
        return value.name
else:
    FieldParameterDataType = QgsProcessingParameterField
    def field_datatype_name(value: int) -> str:   # type: ignore [misc]
        match value:
            case QgsProcessingParameterField.Any:
                field_datatype = 'Any'
            case QgsProcessingParameterField.Numeric:
                field_datatype = 'Numeric'
            case QgsProcessingParameterField.String:
                field_datatype = 'String'
            case QgsProcessingParameterField.DateTime:
                field_datatype = 'DateTime'
            case QgsProcessingParameterField.Binary:
                field_datatype = 'Binary'
            case QgsProcessingParameterField.Boolean:
                field_datatype = 'Boolean'
            case _:
                raise ValueError(f"Unexpected field_datatype: {value}")
        return field_datatype


class ParameterField(InputParameter):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterField) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        md.append(MetadataValue(role="dataType", value=field_datatype_name(param.dataType())))
        md.append(MetadataValue(role="defaultToAllFields", value=param.defaultToAllFields()))

        parent_layer_param = param.parentLayerParameterName()
        if parent_layer_param:
            md.append(
                MetadataValue(
                    role="parentLayerParameterName",
                    value=parent_layer_param,
                ),
            )

        return md

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterField,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = str  #

        if param.allowMultiple():
            _type = Annotated[List[_type], Field(min_length=1)]  # type: ignore [misc]

        return _type

#
# QgsProcessingParameterFieldMapping
#


class FieldMapping(BaseModel, extra='allow'):
    name: str
    type_: str = Field(alias="type")
    expression: str


class ParameterFieldMapping(InputParameter):

    @classmethod
    def metadata(cls, param: QgsProcessingParameterFieldMapping) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        parent_layer_param = param.parentLayerParameterName()
        if parent_layer_param:
            md.append(
                MetadataValue(
                    role="parentLayerParameterName",
                    value=parent_layer_param,
                ),
            )

        return md

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterField,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        return Sequence[FieldMapping]

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> Dict:
        _inp = self.validate(inp)
        return self._model.dump_python(_inp, mode='json', by_alias=True, exclude_none=True)


#
# QgisProcessingParameterExpression
#

class ParameterExpression(InputParameter):
    _ParameterType = str

    @classmethod
    def metadata(cls, param: QgsProcessingParameterExpression) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        md.append(MetadataValue(role="expressionType", value=param.expressionType().name))
        parent_layer_parameter = param.parentLayerParameterName()
        if parent_layer_parameter:
            md.append(
                MetadataValue(
                    role="parentLayerParameterName",
                    value=parent_layer_parameter,
                ),
            )

        return md


#
# QgsProcessingParameterBand
#

class ParameterBand(InputParameter):

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        parent_layer_param = param.parentLayerParameterName()
        if parent_layer_param:
            md.append(
                MetadataValue(
                    role="parentLayerParameterName",
                    value=parent_layer_param,
                ),
            )

        return md

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterBand,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = Annotated[int, Field(ge=0)]  #

        if param.allowMultiple():
            _type = Annotated[List[_type], Field(min_length=1)]  # type: ignore [misc]

        return _type


#
# QgsProcessingParameterAggregate
#

# See analyzing/processing/qgsalgorithmaggregate.cpp
class AggregateItem(BaseModel, extra='allow'):
    name: str
    type_: str = Field(alias='type')
    type_name: Optional[str] = NullField()
    sub_type: Optional[int] = NullField()
    input_: str = Field(alias='input')
    aggregate: str
    length: Optional[int] = NullField()
    precision: Optional[int] = NullField()
    delimiter: Optional[str] = NullField()


class ParameterAggregate(InputParameter):
    _ParameterType = Sequence[AggregateItem]

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        md = super(cls, cls).metadata(param)
        parent_layer_param = param.parentLayerParameterName()
        if parent_layer_param:
            md.append(
                MetadataValue(
                    role="parentLayerParameterName",
                    value=parent_layer_param,
                ),
            )

        return md

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> Dict:
        _inp = self.validate(inp)
        return self._model.dump_python(_inp, mode='json', by_alias=True, exclude_none=True)


#
# QgsProcessingParameterAlignRasterLayers
#


class ParameterAlignRasterLayers(InputParameter):

    @classmethod
    def create_model(
        cls,
        param: QgsProcessingParameterField,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:

        _type: Any = str
        if project:
            allowed_layers = layer_names_from_context(
                project,
                (ProcessingSourceType.Raster,),
                True,
            )
            if allowed_layers:
                _type = Literal[allowed_layers]  # type: ignore [valid-type]

        class AlignRasterItem(BaseModel):
            inputFile: _type
            outputFile: str
            resampleMethod: int

        return Sequence[_type] | Sequence[AlignRasterItem]  # type: ignore [return-value]

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> Dict:
        _inp = self.validate(inp)
        return self._model.dump_python(_inp, mode='json', by_alias=True, exclude_none=True)
