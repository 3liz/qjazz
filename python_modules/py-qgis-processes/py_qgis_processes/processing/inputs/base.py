
from pydantic import Field, JsonValue, TypeAdapter
from typing_extensions import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    Generic,
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

from py_qgis_contrib.core.config import confservice
from py_qgis_processes_schemas.models import one_of
from py_qgis_processes_schemas.processes import InputDescription, ValuePassing

from ..config import ProcessingConfig
from ..context import ProcessingContext

ParameterDefinition = TypeVar('ParameterDefinition', bound=QgsProcessingParameterDefinition)

T = TypeVar('T')


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

        annotated = self.model(
            param,
            project,
            validation_only=validation_only,
            config=config,
        )
        self._metadata = annotated.__metadata__[0]
        self._model = TypeAdapter(annotated)

    @property
    def metadata(self) -> Any:  #  noqa ANN401
        return self._metadata

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
        config: Optional[ProcessingConfig] = None,
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

        _type = cls.create_model_with_config(
            param,
            field,
            project,
            validation_only=validation_only,
            config=config or confservice.conf.processing,
        )

        metadata = field.pop('metadata', None)
        return Annotated[_type, metadata, Field(**field)]  # type: ignore [pydantic-field, valid-type]

    @classmethod
    def create_model_with_config(
        cls,
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        *,
        validation_only: bool = False,
        config: ProcessingConfig,
    ) -> Type:
        return cls.create_model(param, field, project, validation_only=validation_only)

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

        schema = self.json_schema()
        value_passing = self.value_passing()

        return InputDescription(
            title=title,
            description=description,
            schema=schema,
            value_passing=value_passing,
            **kwargs,
        )
