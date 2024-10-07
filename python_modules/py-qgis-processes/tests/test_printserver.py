
from py_qgis_printserver.getprint import (
    GetPrintProcess,
)
from py_qgis_processes.schemas import JobExecute


def test_getprint_parameters_schema(projects):

    project = projects.get('/france/france_parts')

    proc = GetPrintProcess.description(project)

    print("\n==test_getprint_parameters:description\n", proc.model_dump_json(indent=4))
    layers_schema = proc.inputs['layers'].schema_
    print("\n==test_getprint_parameters:layers::schema\n", layers_schema)
    assert layers_schema['type'] == "array"
    assert layers_schema['uniqueItems']
    assert layers_schema['items']['type'] == "string"
    assert len(layers_schema['items']['enum']) == 3


def test_getprint_parameters_query_params():

    from urllib.parse import urlencode

    inputs = dict(
        template="MyLayout",
        crs="EPSG:4326",
        layers=["layers1", "layers2"],
        styles=["style1", "default"],
        transparent=True,
    )

    outputs = {
        "output": {"format": {"mediaType": "application/pdf"}},
    }

    options = JobExecute.model_validate({"inputs": inputs, "outputs": outputs})

    params = tuple(GetPrintProcess.parameters(options))
    print("\n==test_getprint_parameters_query_params\n", urlencode(params))
