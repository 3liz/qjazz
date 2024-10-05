from py_qgis_printserver.getprint import (
    GetPrintProcess,
)


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
