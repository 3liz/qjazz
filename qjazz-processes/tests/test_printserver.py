from pathlib import Path

import pytest

from qgis.server import QgsServer

from qjazz_printserver.getprint import (
    Format,
    GetPrintProcess,
)
from qjazz_processes.processing.prelude import ProcessingContext
from qjazz_processes.schemas import JobExecute

from .utils import FeedBack, Projects


def test_getprint_process_description(projects):
    project = projects.get("/montpellier/montpellier.qgs")

    proc = GetPrintProcess.description(project)

    print("\n==test_getprint_parameters:description\n", proc.model_dump_json(indent=4))
    layers_schema = proc.inputs["layers"].schema_
    print("\n==test_getprint_parameters:layers::schema\n", layers_schema)
    assert layers_schema["type"] == "array"
    assert layers_schema["uniqueItems"]
    assert layers_schema["items"]["type"] == "string"
    assert len(layers_schema["items"]["enum"]) == 18

    template_schema = proc.inputs["template"].schema_
    print("\n==test_getprint_parameters:template::schema\n", template_schema)
    assert template_schema["type"] == "string"
    assert len(template_schema["enum"]) == 2


def test_getprint_parameters():
    from urllib.parse import urlencode

    inputs = dict(
        template="Landscape A4",
        crs="EPSG:3857",
        transparent=True,
    )

    outputs = {
        "output": {"format": {"mediaType": "application/pdf"}},
    }

    options = JobExecute.model_validate({"inputs": inputs, "outputs": outputs})

    query = dict(GetPrintProcess.parameters(options))
    print("\n==test_getprint_parameters_query_params\n", urlencode(query))
    assert query["TEMPLATE"] == "Landscape A4"
    assert query["TRANSPARENT"] == "TRUE"
    assert query["FORMAT"] == "application/pdf"


@pytest.mark.parametrize(
    "output_format",
    (of for of in GetPrintProcess.output_formats),
)
def test_getprint_execute(
    output_format: Format,
    context: ProcessingContext,
    projects: Projects,
    feedback: FeedBack,
    server: QgsServer,
):
    context.job_id = f"test_getprint_{output_format.suffix.removeprefix('.')}"
    context.workdir.mkdir(exist_ok=True)

    inputs = dict(
        template="Landscape A4",
        crs="EPSG:3857",
        transparent=False,
        layers=[
            "SousQuartiers",
            "VilleMTP_MTP_Quartiers_2011_4326",
            "Quartiers",
            "bus",
            "bus_stops"
        ],
    )

    outputs = {
        "output": {"format": {"mediaType": output_format.media_type}},
    }

    request = JobExecute.model_validate({"inputs": inputs, "outputs": outputs})
    project = projects.get("/montpellier/montpellier.qgs")

    context.setProject(project)

    results = GetPrintProcess.execute(
        request,
        feedback,
        context,
        server,
    )
    print("\n==test_getprint_execute::results\n", results)
    assert results["output"]["type"] == output_format.media_type

    output_file = context.workdir.joinpath(Path(results["output"]["href"]).name)
    assert output_file.exists()
