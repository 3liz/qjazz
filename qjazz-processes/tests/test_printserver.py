from pathlib import Path

import pytest

from pydantic import TypeAdapter

from qgis.server import QgsServer

from qjazz_printserver.getprint import (
    Format,
    GetPrintProcess,
)
from qjazz_processes.processing.prelude import ProcessingContext
from qjazz_processes.schemas import JobExecute

from .utils import FeedBack, Projects


def test_getprint_description(projects: Projects):
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
    assert len(template_schema["enum"]) == 3


def test_getprint_composers(projects: Projects):
    from qjazz_printserver.composers import Composer, get_composers

    project = projects.get("/montpellier/montpellier.qgs")

    composers = tuple(get_composers(project))
    print("\n==test_getprint_composers::\n",
        TypeAdapter(tuple[Composer, ...]).dump_json(
            composers,
            indent=4,
            exclude_none=True,
        ).decode(),
    )

    assert len(composers) == 3


def test_getprint_parameters():
    from urllib.parse import urlencode

    inputs = dict(
        template="Landscape A4",
        crs="EPSG:3857",
        transparent=True,
        map_options={
            "map0": dict(layers=["Quartiers"]),
        }
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
    """Test execution with no extent specified.
    The result should show the default extent from the composer definition
    """
    context.job_id = f"test_getprint_{output_format.suffix.removeprefix('.')}"
    context.workdir.mkdir(exist_ok=True)

    layers = [
            "Quartiers",
            "publicbuildings",
            "tramway",
            "tramstop",
            "points_of_interest",
    ]

    inputs = dict(
        template="Landscape A4",
        crs="EPSG:3857",
        transparent=True,
        dpi=72,
        map_options={
            "map0": dict(
                layers=layers,
                # extent=[417006.6137375999, 5394910.340902998, 447158.04891101, 5414844.9948054],
            ),
            "map1": dict(
                # extent=[427360.3486143679, 5403429.440561879, 433285.3486143679, 5408204.440561879],
            ),
        }
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
