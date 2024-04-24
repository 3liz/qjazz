
from pydantic import Field, JsonValue, TypeAdapter
from qgis.core import (
    QgsProcessingParameterDefinition,
    QgsProject,
)
from qgis.PyQt.QtCore import QVariant
from typing_extensions import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    Generic,
    Optional,
    Self,
    Type,
    TypeVar,
)

from py_qgis_processes_schemas.processes import InputDescription

ParameterDefinition = TypeVar('ParameterDefinition', bound=QgsProcessingParameterDefinition)

T = TypeVar('T')


class InputParameter(Generic[T]):

    _ParameterType: ClassVar[Optional[Type]] = None

    def __init__(self,
            param: ParameterDefinition,
            project: Optional[QgsProject] = None,
            validation_only: bool = False,
        ):
        self._param = param
        self._model = self.model(
            param,
            project,
            validation_only,
        )

    def validate(self, inp: JsonValue) -> T:
        return self._model.validate_python(inp)

    def value(self, inp: JsonValue, project: Optional[QgsProject] = None) -> T:
        return self.validate(inp)

    @classmethod
    def model(
        cls: Type[Self],
        param: ParameterDefinition,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> TypeAdapter:

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

        _type = cls.create_model(param, field, project, validation_only)

        return TypeAdapter(Annotated[_type, Field(**field)])  # type: ignore [pydantic-field, valid-type]

    @classmethod
    def create_model(
        cls: Type[Self],
        param: ParameterDefinition,
        field: Dict,
        project: Optional[QgsProject] = None,
        validation_only: bool = False,
    ) -> Type:
        if cls._ParameterType is None:  # type: ignore [attr-defined]
            raise NotImplementedError()
        return cls._ParameterType  # type: ignore [attr-defined]

    def json_schema(self) -> Dict[str, JsonValue]:
        """ Create json schema
        """
        schema = self._model.json_schema()
        schema.pop('title', None)

        if 'anyOf' in schema:
            # See https://github.com/pydantic/pydantic/issues/656#
            schema['oneOf'] = schema['anyOf']
            del schema['anyOf']

        return schema

    def description(self) -> InputDescription:
        """ Parse processing paramater definition to InputDescription
        """
        param = self._param

        flags = int(param.flags())
        # hidden = flags & QgsProcessingParameterDefinition.FlagHidden != 0
        # if hidden:
        #    return None

        kwargs: Dict[str, Any] = {}

        optional = flags & QgsProcessingParameterDefinition.FlagOptional != 0
        if optional:
            kwargs.update(min_occurs=0)

        title = param.description() or param.name().capitalize().replace('_', ' ')
        description = param.help()

        schema = self.json_schema()

        return InputDescription(
            title=title,
            description=description,
            schema=schema,
            **kwargs,
        )
