
import random
import string

from qgis.core import (
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
)

from qjazz_processes.processing.context import (
    ProcessingConfig,
    ProcessingContext,
)
from qjazz_processes.processing.inputs import (
    InputParameter,
    ParameterFile,
    ParameterFileDestination,
)


def test_parameter_file(processing_config: ProcessingConfig):

    context = ProcessingContext(processing_config)
    context.job_id = "test_parameter_file"

    context.workdir.mkdir(exist_ok=True)

    param = QgsProcessingParameterFile("test_parameter_file", extension=".txt")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFile)

    schema = inp.json_schema()
    print("\ntest_parameter_file::schema", schema)

    description = inp.description()
    print("test_parameter_file::description", description)
    assert description.value_passing == ('byValue', 'byReference')

    expected = context.workdir.joinpath(param.name()).with_suffix('.txt')
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


def test_parameter_raw_file(processing_raw_config: ProcessingConfig):
    """ Test input ref from local file system
    """

    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_file"

    raw_destination_path = processing_raw_config.raw_destination_root_path

    param = QgsProcessingParameterFile("test_parameter_raw_file", extension=".txt")

    inp = InputParameter(param)

    input_file = raw_destination_path.joinpath(param.name()).with_suffix('.txt')
    with input_file.open('w') as f:
        f.write("hello world")

    value = inp.value(
        {
            "href": f"file:///{input_file.name}",
        },
        context,
    )
    print("\ntest_parameter_file::value", value)
    assert str(input_file) == value


def test_parameter_filedestination(qgis_session: ProcessingConfig):

    context = ProcessingContext(qgis_session)

    param = QgsProcessingParameterFileDestination("test_parameter_filedestination")

    param.setFileFilter('Text files (*.txt)')

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFileDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_file::schema", schema)

    expected = context.workdir.joinpath(param.name()).with_suffix('.txt')

    value = inp.value(param.name(), context)

    assert str(expected) == value
