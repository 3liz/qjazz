
from types import SimpleNamespace

from pydantic import Field, JsonValue, TypeAdapter
from typing_extensions import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    Type,
    TypeAlias,
    TypeVar,
)

from qgis.core import (
    QgsProcessingParameterDefinition,
    QgsProject,
)
from qgis.PyQt.QtCore import QVariant

from py_qgis_processes_schemas import (
    InputDescription,
    Metadata,
    MetadataValue,
    ValuePassing,
)
from py_qgis_processes_schemas.models import one_of

from ..config import ProcessingConfig
from ..context import ProcessingContext

ParameterDefinition = TypeVar('ParameterDefinition', bound=QgsProcessingParameterDefinition)

T = TypeVar('T')


class InputMeta(SimpleNamespace):
    pass


class InputParameter(Generic[T]):

    _ParameterType: ClassVar[Optional[Type]] = None

    def __init__(self,
            param: ParameterDefinition,
            project: Optional[QgsProject] = None,
            *,
            validation_only: bool = False,
            config: Optional[ProcessingConfig] = None,
        ):
        self._param = param

        annotated = self.model(param, project, validation_only=validation_only)

        self._meta = annotated.__metadata__[0]
        self._model = TypeAdapter(annotated)

    @classmethod
    def metadata(cls, param: ParameterDefinition) -> List[Metadata]:
        return [MetadataValue(role="typeName", value=param.type())]

    @classmethod
    def keywords(cls, parame: ParameterDefinition) -> List[str]:
        return []

    @property
    def meta(self) -> InputMeta:
        return self._meta

    def value_passing(self) -> ValuePassing:
        return ('byValue',)

    def validate(self, inp: JsonValue) -> T:
        return self._model.validate_python(inp)

    def value(self, inp: JsonValue, context: Optional[ProcessingContext] = None) -> T:
        return self.validate(inp)

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
            # Handle defaultValue
            # XXX In some case QVariant are
            # not converted to python object (SIP bug ?)
            # Problem stated in getting QgsProcessingParameterFeatureSource
            # from processing.core.parameters.getParameterFromString
            default = param.defaultValue()
            if isinstance(default, QVariant):
                default = None if default.isNull() else default.value()

            if default is not None:
                field.update(default=default)

        _type = cls.create_model(param, field, project, validation_only=validation_only)

        meta = field.pop('meta', None)
        return Annotated[_type, meta, Field(**field)]  # type: ignore [pydantic-field, valid-type]

    @classmethod
    def create_model(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:
        if cls._ParameterType is None:  # type: ignore [attr-defined]
            raise NotImplementedError()
        return cls._ParameterType  # type: ignore [attr-defined]

    @classmethod
    def visible(cls, param: ParameterDefinition, project: Optional[QgsProject] = None) -> bool:
        flags = int(param.flags())
        return flags & QgsProcessingParameterDefinition.FlagHidden == 0

    def json_schema(self) -> Dict[str, JsonValue]:
        """ Create json schema
        """
        schema = self._model.json_schema()
        schema.pop('title', None)

        one_of(schema)

        return schema

    def description(self) -> InputDescription:
        """ Parse processing paramater definition to InputDescription
        """
        param = self._param

        flags = int(param.flags())

        kwargs: Dict[str, Any] = {}

        optional = flags & QgsProcessingParameterDefinition.FlagOptional != 0
        if optional:
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
