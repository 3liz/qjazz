from pathlib import Path

import pytest

from qgis.server import QgsServer

from qjazz_processes.processing.prelude import ProcessingContext
from qjazz_processes.schemas import JobExecute
from qjazz_wfsoutputserver.wfsoutput import (
    WfsOutputFormat,
    WfsOutputParameters,
    WfsOutputProcess,
)

from .utils import FeedBack, Projects


def test_wfsoutput_process_description(projects: Projects):
    project = projects.get("/france/france_parts")

    proc = WfsOutputProcess.description(project)

    print("\n==test_wfsoutput_parameters:description\n", proc.model_dump_json(indent=4))
    layers_schema = proc.inputs["layer"].schema_
    print("\n==test_getprint_parameters:layers::schema\n", layers_schema)
    assert layers_schema["type"] == "string"
    assert len(layers_schema["enum"]) == 3


def test_wfsoutput_parameters():

    inputs = dict(
        layer="france_parts",
    )

    outputs = {
        "output": {"format": {"mediaType": "application/x-fgb"}},
    }

    request = JobExecute.model_validate({"inputs": inputs, "outputs": outputs})

    output_format = WfsOutputProcess.output_format(request)
    print("\n==test_wfsoutput_parameters::format::\n", output_format)
    assert output_format == WfsOutputFormat.FGB

    params = WfsOutputParameters.model_validate(request.inputs)
    print("\n==test_wfsoutput_parameters::params::\n", params)
    query = dict(params.query(output_format))
    print("\n==test_wfsoutput_parameters::query::\n", query)
    assert query["TYPENAME"] == "france_parts"


@pytest.mark.parametrize(
    "output_format", (of for of in WfsOutputFormat)
)
def test_wfsoutput_execute(
    output_format: WfsOutputFormat,
    context: ProcessingContext,
    projects: Projects,
    feedback: FeedBack,
    server: QgsServer,
):
    context.job_id = f"test_wfsoutput_{output_format.name.lower()}"
    context.workdir.mkdir(exist_ok=True)

    inputs = dict(
        layer="lines",
    )

    outputs = {
        "output": {"format": {"mediaType": output_format.value.media_type}},
    }

    request = JobExecute.model_validate({"inputs": inputs, "outputs": outputs})
    project = projects.get("/lines/lines.qgs")

    context.setProject(project)

    results = WfsOutputProcess.execute(
        request,
        feedback,
        context,
        server,
    )
    print("\n==test_wfsoutput_execute::results\n", results)
    assert results["output"]["type"] == output_format.value.media_type

    assert WfsOutputProcess.output_format(request) == output_format

    output_file = context.workdir.joinpath(Path(results["output"]["href"]).name)
    assert output_file.exists()

    if output_format.value.archive:
        assert output_file.suffix == ".zip"
    else:
        assert output_file.suffix == output_format.value.suffix
