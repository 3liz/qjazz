
import traceback

from functools import cached_property
from typing import (
    Annotated,
    Generic,
    Optional,
    Sequence,
    TypeAlias,
    TypeVar,
)

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingOutputDefinition,
    QgsProcessingParameterDefinition,
)

from qjazz_contrib.core import logger
from qjazz_processes.schemas import (
    Format,
    InputValueError,
    JsonDict,
    Metadata,
    MetadataValue,
    Output,
    OutputDescription,
    OutputFormatDefinition,
    ValuePassing,
    remove_auto_title,
)
from qjazz_processes.schemas.models import one_of

from ..context import ProcessingContext
from ..inputs import InputParameterDef

OutputDefinition = TypeVar('OutputDefinition', bound=QgsProcessingOutputDefinition)

T = TypeVar('T')


class OutputParameter(Generic[T]):

    _Model: TypeAlias | None = None

    def __init__(self,
        out: OutputDefinition,
        alg: Optional[QgsProcessingAlgorithm] = None,
    ):
        self._out = out
        self._alg = alg
        self.initialize()

    def initialize(self):
        pass

    @property
    def name(self) -> str:
        return self._out.name()

    @property
    def algorithm(self) -> Optional[QgsProcessingAlgorithm]:
        return self._alg

    @classmethod
    def hidden(cls, outp: OutputDefinition) -> bool:
        return False

    @classmethod
    def metadata(cls, outp: OutputDefinition) -> list[Metadata]:
        return [MetadataValue(role="typeName", value=outp.type())]

    @classmethod
    def keywords(cls, outp: OutputDefinition) -> list[str]:
        return []

    def value_passing(self) -> ValuePassing:
        return ('byValue',)

    @classmethod
    def model(
        cls,
        outp: OutputDefinition,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> TypeAlias:

        field: dict = {}
        _type = cls.create_model(outp, field, alg)

        return Annotated[_type, Field(**field)]  # type: ignore [pydantic-field, valid-type]

    @classmethod
    def create_model(
        cls,
        outp: OutputDefinition,
        field: dict,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> TypeAlias:
        if cls._Model is None:  # type: ignore [attr-defined]
            raise NotImplementedError()
        return cls._Model  # type: ignore [attr-defined]

    def json_schema(self) -> JsonDict:
        schema = self._model.json_schema()
        schema.pop('title', None)
        one_of(schema)
        remove_auto_title(schema)
        return schema

    @cached_property
    def _model(self):
        return TypeAdapter(self.model(self._out, self._alg))

    @property
    def title(self) -> str:
        return self._out.name().capitalize().replace('_', ' ')

    def description(self) -> OutputDescription:
        """ Parse processing output definition to OutputDescription
        """
        outp = self._out

        return OutputDescription(
            title=self.title,
            description=outp.description(),
            schema=self.json_schema(),
            metadata=self.metadata(outp),
            keywords=self.keywords(outp),
            value_passing=self.value_passing(),
        )

    @classmethod
    def get_output_formats(
        cls,
        outdef: OutputDefinition,
        alg: QgsProcessingAlgorithm,
    ) -> Sequence[Format]:

        return ()

    @cached_property
    def allowed_formats(self) -> Sequence[Format]:
        return self.get_output_formats(self._out, self._alg)

    @classmethod
    def get_input_definition(
        cls,
        out: OutputDefinition,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> Optional[QgsProcessingParameterDefinition]:
        """ Returns the parameter name of the input destination name
            that have created this output definition
        """
        if out.autoCreated():
            return alg and alg.parameterDefinition(out.name())
        else:
            return None

    @property
    def input_definition(self) -> Optional[QgsProcessingParameterDefinition]:
        return self.get_input_definition(self._out, self._alg)

    @property
    def format_definition(self) -> Optional[OutputFormatDefinition]:
        return self if isinstance(self, OutputFormatDefinition) else None

    def validate_output(self, out: Output, param: Optional[InputParameterDef] = None):
        """ Validate output json declaration

            Note that output declaration for processes/execute command
            are limited to a `format` declaration
        """
        if isinstance(self, OutputFormatDefinition):
            try:
                self.output_format = out.format
            except ValidationError:
                logger.error(traceback.format_exc())
                raise InputValueError(f"{self._out.name()}: Invalid format definition")

            # Test if format is in allowed_formats
            if self.output_format not in self.allowed_formats:
                raise InputValueError(f"{self._out.name()}: invalid format '{self.output_format}'")

    def dump_json(self, value: T) -> JsonValue:
        return self._model.dump_python(value, mode='json', by_alias=True, exclude_none=True)

    def output(self, value: T, context: ProcessingContext) -> JsonValue:
        """ Dump output value to a json compatible format
        """
        return self.dump_json(value)
