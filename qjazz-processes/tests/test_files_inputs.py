import json
import random
import string

import pytest

from pydantic import ValidationError

from qgis.core import (
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFolderDestination,
)

from qjazz_processes.processing.context import (
    ProcessingConfig,
    ProcessingContext,
)
from qjazz_processes.processing.inputs import (
    InputParameter,
    ParameterFile,
    ParameterFileDestination,
    ParameterFolderDestination,
)
from qjazz_processes.schemas import InputValueError

# TODO: Test Qualified input value
# TODO: Test Reference input value


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
    assert description.value_passing == ("byValue", "byReference")

    expected = context.workdir.joinpath(param.name()).with_suffix(".txt")
    if expected.exists():
        expected.unlink()

    ascii_content = "".join(random.choices(string.ascii_letters, k=20))  # noqa S311

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
    with expected.open("r") as f:
        assert f.read() == ascii_content


def test_parameter_raw_file(processing_raw_config: ProcessingConfig):
    """Test input ref from local file system"""

    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_file"

    raw_destination_path = processing_raw_config.raw_destination_root_path
    assert raw_destination_path is not None

    param = QgsProcessingParameterFile("test_parameter_raw_file", extension=".txt")

    inp = InputParameter(param)

    input_file = raw_destination_path.joinpath(param.name()).with_suffix(".txt")
    with input_file.open("w") as f:
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

    param.setFileFilter("Text files (*.txt)")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFileDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_filedestination::schema", schema)

    # Check output formats metadata
    output_formats_md = next(md.value for md in inp.metadata(param) if md.role == "outputFormats")  # type: ignore [union-attr]

    print("\ntest_parameter_filedestination::formats", output_formats_md)
    assert isinstance(output_formats_md, list)
    assert len(output_formats_md) == 1
    assert output_formats_md[0] == "text/plain"

    expected = context.workdir.joinpath(param.name()).with_suffix(".txt")

    value = inp.value(param.name(), context)

    assert str(expected) == value


def test_parameter_raw_file_traversal(processing_raw_config: ProcessingConfig):
    """Raw file references cannot escape the root folder"""
    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_file_traversal"

    param = QgsProcessingParameterFile("test_parameter_raw_file_traversal", extension=".txt")
    inp = InputParameter(param)

    # Root folder is the tests '__workdir__' folder: use an existing file
    # outside the root folder
    root_path = processing_raw_config.raw_destination_root_path
    assert root_path is not None
    assert root_path.parent.joinpath("conftest.py").exists()

    for href in ("file:///../conftest.py", "file:///foo/../../conftest.py"):
        with pytest.raises(InputValueError, match="Invalid path"):
            inp.value({"href": href}, context)


def test_parameter_filedestination_traversal(processing_config: ProcessingConfig):
    """Destination paths escaping the job folder are truncated"""
    context = ProcessingContext(processing_config)
    context.job_id = "test_parameter_filedestination_traversal"

    param = QgsProcessingParameterFileDestination("test_parameter_filedestination_traversal")
    param.setFileFilter("Text files (*.txt)")

    inp = InputParameter(param)

    workdir = context.workdir

    assert inp.value("foo/bar.txt", context) == str(workdir.joinpath("foo", "bar.txt"))
    assert inp.value("foo/../bar.txt", context) == str(workdir.joinpath("bar.txt"))
    # Truncated to file name in job folder
    assert inp.value("../../x/bar.txt", context) == str(workdir.joinpath("bar.txt"))


def test_parameter_raw_filedestination(processing_raw_config: ProcessingConfig):
    """Raw destination paths are resolved against the root folder"""
    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_filedestination"

    root_path = processing_raw_config.raw_destination_root_path
    assert root_path is not None

    param = QgsProcessingParameterFileDestination("test_parameter_raw_filedestination")
    param.setFileFilter("Text files (*.txt)")

    inp = InputParameter(param)

    assert inp.value("/foo/bar.txt", context) == str(root_path.joinpath("foo", "bar.txt"))
    assert inp.value("bar.txt", context) == str(context.workdir.joinpath("bar.txt"))

    for value in ("/../bar.txt", "../../bar.txt"):
        with pytest.raises(InputValueError):
            inp.value(value, context)


@pytest.mark.parametrize(
    "extension,suffix,media_type",
    [
        ("csv", ".csv", "text/csv"),
        (".csv", ".csv", "text/csv"),
        ("", "", "application/octet-stream"),
    ],
)
def test_parameter_file_extension(
    processing_config: ProcessingConfig,
    extension: str,
    suffix: str,
    media_type: str,
):
    """QGIS file extension may be given with or without leading dot"""
    context = ProcessingContext(processing_config)
    context.job_id = "test_parameter_file_extension"
    context.workdir.mkdir(exist_ok=True)

    param = QgsProcessingParameterFile("test_parameter_file_extension", extension=extension)
    inp = InputParameter(param)

    schema = json.dumps(inp.json_schema())
    print("\ntest_parameter_file_extension::schema", schema)
    assert f'"contentMediaType": "{media_type}"' in schema

    value = inp.value({"mediaType": media_type, "value": "a,b\n1,2"}, context)

    expected = context.workdir.joinpath(param.name()).with_suffix(suffix)
    assert value == str(expected)
    assert expected.read_text() == "a,b\n1,2"


def test_parameter_raw_file_extension(processing_raw_config: ProcessingConfig):
    """Raw file reference without extension get the QGIS extension"""
    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_file_extension"

    root_path = processing_raw_config.raw_destination_root_path
    assert root_path is not None

    input_file = root_path.joinpath("test_parameter_raw_file_extension.csv")
    input_file.write_text("a,b\n1,2")

    param = QgsProcessingParameterFile("test_parameter_raw_file_extension", extension="csv")
    inp = InputParameter(param)

    value = inp.value({"href": "file:///test_parameter_raw_file_extension"}, context)
    assert value == str(input_file)


def test_parameter_folderdestination(processing_config: ProcessingConfig):
    """Folder destinations are located in the job folder"""
    context = ProcessingContext(processing_config)
    context.job_id = "test_parameter_folderdestination"

    param = QgsProcessingParameterFolderDestination("OUTPUT", defaultValue="results")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterFolderDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_folderdestination::schema", schema)
    assert schema["type"] == "string"
    assert schema["default"] == "results"

    workdir = context.workdir

    assert inp.value("out", context) == str(workdir.joinpath("out"))
    assert inp.value("a/../b", context) == str(workdir.joinpath("b"))
    # Truncated to its name in the job folder
    assert inp.value("../../x", context) == str(workdir.joinpath("x"))

    with pytest.raises(ValidationError):
        inp.value(1, context)

    # Execution path
    inp = InputParameter(param, validation_only=True)
    parameters = InputParameter.parameters([inp], {"OUTPUT": "out"}, context)
    assert parameters == {"OUTPUT": str(workdir.joinpath("out"))}


def test_parameter_raw_folderdestination(processing_raw_config: ProcessingConfig):
    """Raw folder destinations are confined to the root folder"""
    context = ProcessingContext(processing_raw_config)
    context.job_id = "test_parameter_raw_folderdestination"

    root_path = processing_raw_config.raw_destination_root_path
    assert root_path is not None

    inp = InputParameter(QgsProcessingParameterFolderDestination("OUTPUT"))

    assert inp.value("/foo/out", context) == str(root_path.joinpath("foo", "out"))
    assert inp.value("out", context) == str(context.workdir.joinpath("out"))

    for value in ("/../out", "../../out"):
        with pytest.raises(InputValueError):
            inp.value(value, context)
