from pathlib import Path
from typing import cast

import pytest

from qjazz_core.condition import PostconditionError

from qgis.core import (
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputHtml,
)

from qjazz_processes.processing.context import (
    ProcessingConfig,
    ProcessingContext,
)
from qjazz_processes.processing.inputs import InputParameter
from qjazz_processes.processing.outputs import (
    OutputFile,
    OutputFolder,
    OutputHtml,
    OutputParameter,
)
from qjazz_processes.processing.outputs.files import resolve_path
from qjazz_processes.schemas import (
    InputValueError,
    Output,
    OutputFormatDefinition,
)


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

    assert isinstance(param, OutputFormatDefinition)

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


def test_output_resolve_path(processing_config: ProcessingConfig):
    """Output paths must be located in the job folder"""
    context = ProcessingContext(processing_config)
    context.job_id = "test_output_resolve_path"

    workdir = context.workdir

    # Relative paths are resolved against the job folder
    assert resolve_path("output.json", context) == workdir.joinpath("output.json")
    assert resolve_path("foo/../output.json", context) == workdir.joinpath("output.json")
    assert resolve_path(str(workdir.joinpath("output.json")), context) == workdir.joinpath("output.json")

    for value in ("../output.json", str(workdir.joinpath("..", "output.json")), "/etc/passwd"):
        with pytest.raises(PostconditionError):
            resolve_path(value, context)


def test_output_resolve_raw_path(processing_config: ProcessingConfig, tmp_path: Path):
    """Raw output paths may be located in the raw destination root folder"""
    context = ProcessingContext(
        processing_config.model_copy(
            update={
                "raw_destination_input_sink": True,
                "raw_destination_root_path": tmp_path,
            },
        ),
    )
    context.job_id = "test_output_resolve_raw_path"

    assert resolve_path("output.json", context) == context.workdir.joinpath("output.json")
    assert resolve_path(str(tmp_path / "output.json"), context) == tmp_path / "output.json"

    with pytest.raises(PostconditionError):
        resolve_path(str(tmp_path / ".." / "output.json"), context)


def test_output_file_link(qgis_session: ProcessingConfig):
    """Output file returns a link with the output description"""
    context = ProcessingContext(qgis_session)
    context.job_id = "test_output_file_link"
    context.workdir.mkdir(parents=True, exist_ok=True)

    context.workdir.joinpath("output.json").write_text('{"foo": "bar"}')

    output = OutputParameter(QgsProcessingOutputFile("OUTPUT", "Output file"))
    assert isinstance(output, OutputFile)

    link = output.output("output.json", context)
    print("\ntest_output_file_link::link", link)

    assert isinstance(link, dict)
    assert link["description"] == "Output file"
    assert link["length"] == len('{"foo": "bar"}')
    assert cast("str", link["href"]).endswith("output.json")


def test_output_folder_link(qgis_session: ProcessingConfig):
    """Output folder returns a link with the output description"""
    context = ProcessingContext(qgis_session)
    context.job_id = "test_output_folder_link"
    context.workdir.joinpath("folder").mkdir(parents=True, exist_ok=True)

    output = OutputParameter(QgsProcessingOutputFolder("OUTPUT", "Output folder"))
    assert isinstance(output, OutputFolder)

    link = output.output("folder", context)
    print("\ntest_output_folder_link::link", link)

    assert isinstance(link, dict)
    assert link["description"] == "Output folder"


def test_output_html_link(qgis_session: ProcessingConfig):
    """Output html returns a link to the html file"""
    context = ProcessingContext(qgis_session)
    context.job_id = "test_output_html_link"
    context.workdir.mkdir(parents=True, exist_ok=True)

    content = "<html><body>Hello</body></html>"
    context.workdir.joinpath("report.html").write_text(content)

    output = OutputParameter(QgsProcessingOutputHtml("OUTPUT", "Html report"))
    assert isinstance(output, OutputHtml)

    link = output.output("report.html", context)
    print("\ntest_output_html_link::link", link)

    assert isinstance(link, dict)
    assert link["type"] == "text/html"
    assert link["description"] == "Html report"
    assert link["length"] == len(content)
    assert cast("str", link["href"]).endswith("report.html")

    # Html output must be a file
    context.workdir.joinpath("folder").mkdir(exist_ok=True)
    with pytest.raises(FileNotFoundError):
        output.output("folder", context)
