from datetime import datetime

import pytest

from pydantic import ValidationError

from qgis.core import (
    QgsMeshDatasetGroupMetadata,
    QgsProcessingParameterMeshDatasetGroups,
    QgsProcessingParameterMeshDatasetTime,
    QgsProcessingParameterMeshLayer,
)

from qjazz_processes.processing.inputs import (
    InputParameter,
    ParameterMeshDatasetGroups,
    ParameterMeshDatasetTime,
)


def test_parameter_meshlayer():
    param = QgsProcessingParameterMeshLayer("Mesh")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_mesh::", schema)


def test_parameter_meshdatasetgroups():
    param = QgsProcessingParameterMeshDatasetGroups(
        "MeshDatasetGroups",
        meshLayerParameterName="Mesh",
        supportedDataType=[
            QgsMeshDatasetGroupMetadata.DataType.DataOnVertices,
            QgsMeshDatasetGroupMetadata.DataType.DataOnFaces,
        ],
    )

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMeshDatasetGroups)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_meshdatasetgroups::", schema)
    assert schema["type"] == "array"
    assert schema["items"] == {"type": "integer", "minimum": 0}
    assert schema["minItems"] == 1

    # Values are dataset group indexes
    value = inp.value([0, 5, 7])
    assert value == [0, 5, 7]
    assert param.checkValueIsAcceptable(value)
    assert QgsProcessingParameterMeshDatasetGroups.valueAsDatasetGroup(value) == [0, 5, 7]

    for invalid in ([], [-1], ["a"]):
        with pytest.raises(ValidationError):
            inp.value(invalid)

    metadata = {md.role: md.value for md in inp.description().metadata}
    assert metadata["meshLayerParameterName"] == "Mesh"
    assert sorted(metadata["supportedDataTypes"]) == ["DataOnFaces", "DataOnVertices"]


def test_parameter_meshdatasettime():
    param = QgsProcessingParameterMeshDatasetTime("MeshDatasetTime")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMeshDatasetTime)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_meshdatasetdatetime::", schema)

    value = inp.value({"type": "defined-date-time", "value": datetime.now()})
    assert param.checkValueIsAcceptable(value)
