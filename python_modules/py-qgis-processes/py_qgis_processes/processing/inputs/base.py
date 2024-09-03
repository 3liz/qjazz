

from pydantic import Field, JsonValue, TypeAdapter
from typing_extensions import (
    Annotated,
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Self,
    TypeAlias,
    TypeVar,
)

from qgis.core import (
    QgsProcessingParameterDefinition,
    QgsProject,
)
from qgis.PyQt.QtCore import QVariant

from py_qgis_processes.schemas import (
    InputDescription,
    JsonDict,
    Metadata,
    MetadataValue,
    ValuePassing,
    remove_auto_title,
)
from py_qgis_processes.schemas.models import one_of

from ..context import ProcessingContext

ParameterDefinition = TypeVar('ParameterDefinition', bound=QgsProcessingParameterDefinition)

T = TypeVar('T')


class InputParameter(Generic[T]):

    _ParameterType: TypeAlias | None = None

    def __init__(
            self,
            param: ParameterDefinition,
            project: Optional[QgsProject] = None,
            *,
            validation_only: bool = False,
        ):

        annotated = self.model(param, project, validation_only=validation_only)
        self._param = param
        self._model = TypeAdapter(annotated)
        self.initialize()

    def initialize(self):
        pass

    def rebind(
        self,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Self:
        """ Duplicate the class and rebind it with
            another project.
        """
        return self.__class__(self._param, project, validation_only=validation_only)

    @property
    def name(self) -> str:
        return self._param.name()

    def optional_default_value(self, context: Optional[ProcessingContext] = None) -> Optional[T]:
        """ Some optional destination parameters may
            force create a output value.
            This is the case with parameters created
            with the model designer.
        """
        # Note: createByDefault is defined for QgsProcessingParameteDestination
        if self._param.isDestination() and self._param.createByDefault():
            return self._param.name()
        else:
            return None

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        return [MetadataValue(role="typeName", value=param.type())]

    @classmethod
    def keywords(cls, param: ParameterDefinition) -> List[str]:
        return []

    def value_passing(self) -> ValuePassing:
        return ('byValue',)

    def validate(self, inp: JsonValue) -> T:
        return self._model.validate_python(inp)

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> T:
        return self.validate(inp)

    @classmethod
    def default_value(cls, param: ParameterDefinition) -> T:
        # Handle defaultValue
        # XXX In some case QVariant are
        # not converted to python object (SIP bug ?)
        # Problem stated in getting QgsProcessingParameterFeatureSource
        # from processing.core.parameters.getParameterFromString
        default = param.defaultValue()
        if isinstance(default, QVariant):
            default = None if default.isNull() else default.value()
        return default

    @classmethod
    def model(
        cls,
        param: ParameterDefinition,
        project: Optional[QgsProject] = None,
        *,
        validation_only: bool = False,
    ) -> TypeAlias:

        field: Dict = {}

        if not validation_only:
            default = cls.default_value(param)
            if default is not None:
                field.update(default=default)

        _type = cls.create_model(param, field, project, validation_only=validation_only)

        return Annotated[_type, Field(**field)]  # type: ignore [pydantic-field, valid-type]

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAlias:
        if cls._ParameterType is None:
            raise NotImplementedError()
        return cls._ParameterType

    @classmethod
    def hidden(cls, param: ParameterDefinition, project: Optional[QgsProject] = None) -> bool:
        return int(param.flags()) & QgsProcessingParameterDefinition.FlagHidden != 0

    @property
    def optional(self) -> bool:
        return int(self._param.flags()) & QgsProcessingParameterDefinition.FlagOptional != 0

    def json_schema(self) -> JsonDict:
        """ Create json schema
        """
        schema = self._model.json_schema()
        schema.pop('title', None)
        one_of(schema)
        remove_auto_title(schema)
        return schema

    def description(self) -> InputDescription:
        """ Parse processing parameter definition to InputDescription
        """
        param = self._param

        kwargs: Dict[str, Any] = {}

        if self.optional:
            kwargs.update(min_occurs=0)

        title = param.description() or param.name().capitalize().replace('_', ' ')
        description = param.help()

        return InputDescription(
            title=title,
            description=description,
            schema=self.json_schema(),
            value_passing=self.value_passing(),
            metadata=self.metadata(param),
            keywords=self.keywords(param),
            **kwargs,
        )
