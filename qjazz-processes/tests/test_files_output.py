import pytest

from qgis.core import (
    QgsProcessingOutputFile,
)

from qjazz_processes.processing.context import (
    ProcessingConfig,
)
from qjazz_processes.processing.inputs import InputParameter
from qjazz_processes.processing.outputs import (
    OutputFile,
    OutputParameter,
)
from qjazz_processes.schemas import InputValueError, Output


def test_output_file(qgis_session: ProcessingConfig):
    # Must be imported once qgis processing is initialized
    # (via qgis_session fixture)
    from .plugins.provider.provider import TestFileDestination

    alg = TestFileDestination()
    alg.initAlgorithm()

    outdef = alg.outputDefinition("OUTPUT")
    assert outdef is not None
    assert isinstance(outdef, QgsProcessingOutputFile)

    output = OutputParameter(outdef, alg)
    assert isinstance(output, OutputFile)

    schema = output.json_schema()
    print("\ntest_output_file::json_schema", schema)

    allowed_formats = output.allowed_formats
    print("test_output_file::allowed_formats", allowed_formats)

    # Validate output format
    inputdef = output.input_definition
    assert inputdef is not None

    param = InputParameter(inputdef)

    # Invalid format should raise InputValueError
    with pytest.raises(InputValueError):
        output.validate_output(
            Output.model_validate({"format": {"mediaType": "application/xml"}}),
            param,
        )

    output.validate_output(
        Output.model_validate({"format": {"mediaType": "application/json"}}),
        param,
    )
    assert output.output_extension == ".json"
    assert param.output_extension == ".json"
