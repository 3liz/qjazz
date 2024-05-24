
import random
import string

from pathlib import Path

from qgis.core import (
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
)

from py_qgis_processes.processing.context import (
    ProcessingConfig,
    ProcessingContext,
)
from py_qgis_processes.processing.inputs import (
    InputParameter,
    ParameterFile,
    ParameterFileDestination,
)


def test_parameter_file(workdir: Path, processing_config: ProcessingConfig):

    context = ProcessingContext(processing_config)
    context.workdir = workdir

    param = QgsProcessingParameterFile("test_parameter_file", extension=".txt")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFile)

    schema = inp.json_schema()
    print("\ntest_parameter_file::schema", schema)

    description = inp.description()
    print("test_parameter_file::description", description)
    assert description.value_passing == ('byValue', 'byReference')

    expected = workdir.joinpath(param.name()).with_suffix('.txt')
    if expected.exists():
        expected.unlink()

    ascii_content = ''.join(random.choices(string.ascii_letters, k=20))

    value = inp.value(
        {
            "mediaType": "text/plain",
            "value": ascii_content,
        },
        context,
    )
    print("test_parameter_file::value", value)

    assert str(expected) == value
    assert expected.exists()
    with expected.open('r') as f:
        assert f.read() == ascii_content


def test_parameter_raw_file(workdir: Path, processing_raw_config: ProcessingConfig):

    context = ProcessingContext(processing_raw_config)
    context.workdir = workdir

    param = QgsProcessingParameterFile("test_parameter_raw_file", extension=".txt")

    inp = InputParameter(param)

    input_file = workdir.joinpath(param.name()).with_suffix('.txt')
    with input_file.open('w') as f:
        f.write("hello_world")

    value = inp.value(
        {
            "href": f"file:///{input_file.name}",
        },
        context,
    )
    print("test_parameter_file::value", value)
    assert str(input_file) == value


def test_parameter_filedestination(workdir: Path, qgis_session: ProcessingConfig):

    context = ProcessingContext(qgis_session)
    context.workdir = workdir

    param = QgsProcessingParameterFileDestination("test_parameter_filedestination")

    param.setFileFilter('Text files (*.txt)')

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFileDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_file::schema", schema)

    expected = workdir.joinpath(param.name()).with_suffix('.txt')

    value = inp.value(param.name(), context)

    assert str(expected) == value
