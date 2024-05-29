# mypy: disable-error-code="has-type"
# Note: mypy cannot resolve multiple inherited property decorated
#
#
# Handle files output
#
import traceback

from pathlib import Path

from pydantic import ValidationError
from typing_extensions import (
    Any,
    Dict,
    Literal,
    Optional,
    Sequence,
    TypeAlias,
)

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFileDestination,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_postcondition
from py_qgis_processes_schemas import (
    AnyFormat,
    Format,
    InputValueError,
    JsonDict,
    Link,
    NullField,
    Output,
    OutputFormat,
    OutputFormatDefinition,
    ValuePassing,
)

from ..utils import output_file_formats
from .base import (
    InputParameterDef,
    JsonValue,
    OutputDefinition,
    OutputParameter,
    ProcessingContext,
)

#
# QgsProcessingOutputFile
#


class OutputFile(OutputParameter, OutputFormatDefinition):  # type: ignore [misc]

    def value_passing(self) -> ValuePassing:
        return ('byReference',)

    @classmethod
    def get_output_formats(
        cls,
        outdef: OutputDefinition,
        alg: QgsProcessingAlgorithm,
    ) -> Sequence[Format]:

        inputdef = cls.get_input_definition(outdef, alg)
        if isinstance(inputdef, QgsProcessingParameterFileDestination):
            return output_file_formats(inputdef)
        else:
            return ()

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

    def validate_output(self, out: JsonDict, param: Optional[InputParameterDef] = None):
        """ Override
        """
        super().validate_output(out, param)

        # Pass format definition to file parameter
        format_definition = self.format_definition
        if format_definition \
            and format_definition.output_format != AnyFormat \
            and isinstance(param, OutputFormatDefinition):
            param.copy_format_from(format_definition)

    def output(
        self, value: str,
        context: ProcessingContext,
    ) -> JsonValue:

        path = resolve_path(value, context)
        if not path.is_file():
            raise FileNotFoundError(value)

        if self.output_format == AnyFormat:
            # Give a chance to get the file format
            self.output_extension = path.suffix

        reference_url = context.file_reference(path)

        return Link(
            href=reference_url,
            mime_type=self.output_format.media_type,
            title=self.title,
            description=self._out.description,
            length=path.stat().st_size,
        ).model_dump(mode='json', by_alias=True, exclude_none=True)


#
# QgsProcessingOutputFolder
#

class OutputFolder(OutputParameter):

    _Model = str

    def value_passing(self) -> ValuePassing:
        return ('byReference',)

    def output(self, value: str, context: Optional[ProcessingContext] = None) -> JsonValue:

        context = context or ProcessingContext()

        path = resolve_path(value, context)
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory")

        reference_url = context.file_reference(path)

        return Link(
            href=reference_url,
            title=self.title,
            description=self._out.description,
        ).model_dump(mode='json', by_alias=True, exclude_none=True)


#
# QgsProcessingOutputHtml
#

class OutputHtml(OutputFile):

    _OutputFormat = Format(media_type="text/html", suffix=".html")

    def initialize(self):
        self.output_format = OutputFormat(media_type=self._OutputFormat.media_type)

    def validate_output(self, out: JsonDict, param: Optional[InputParameterDef] = None):
        try:
            output_format = Output.model_validate(out).format
            if output_format != self.output_format:
                raise InputValueError(f"{self._out.name()}: invalid format '{self.output_format}'")
        except ValidationError:
            logger.error(traceback.format_exc())
            raise InputValueError(f"{self._out.name()}: Invalid format definition")

    @classmethod
    def get_output_formats(
        cls,
        outdef: OutputDefinition,
        alg: QgsProcessingAlgorithm,
    ) -> Sequence[Format]:

        return (cls._OutputFormat,)

    @classmethod
    def create_model(
        cls,
        outp: OutputDefinition,
        field: Dict,
        alg: Optional[QgsProcessingAlgorithm],
    ) -> TypeAlias:

        output_formats = cls.get_output_formats(outp, alg)

        class _Ref(Link):
            mime_type: Optional[  # type: ignore [valid-type]
                Literal[tuple(output_formats)]
            ] = NullField(
                serialization_alias="type",
                json_schema_extra={"readOnly": True},
            )

        return _Ref

    def output(self, value: str, context: Optional[ProcessingContext] = None) -> JsonValue:

        context = context or ProcessingContext()

        path = resolve_path(value, context)
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory")

        reference_url = context.file_reference(path)

        return Link(
            href=reference_url,
            title=self.title,
            description=self._out.description,
        ).model_dump(mode='json', by_alias=True, exclude_none=True)


#
# Utils
#
def resolve_path(value: str, context: Optional[ProcessingContext]) -> Path:
    """ Return either a relative workdir path or an absolute raw path
    """
    workdir = (context and context.workdir) or Path()

    p = Path(value)
    if context and context.config.raw_destination_input_sink:
        assert_postcondition(
            p.is_relative_to(context.raw_destination_root_path) or
            p.is_relative_to(workdir),
            f"Invalid path: {p}",
        )
    else:
        assert_postcondition(
            p.is_relative_to(workdir),
            f"Invalid path: {p}",
        )

    return p
