from datetime import datetime
from typing import cast

import pytest

from pydantic import ValidationError

from qgis.core import (
    QgsMeshDatasetGroupMetadata,
    QgsProcessingParameterMeshDatasetGroups,
    QgsProcessingParameterMeshDatasetTime,
    QgsProcessingParameterMeshLayer,
)

from qjazz_processes.processing.context import ProcessingContext
from qjazz_processes.processing.inputs import (
    InputParameter,
    ParameterMeshDatasetGroups,
    ParameterMeshDatasetTime,
)
from qjazz_processes.schemas import JsonValue, MetadataValue


def test_parameter_meshlayer() -> None:
    param = QgsProcessingParameterMeshLayer("Mesh")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_mesh::", schema)


def test_parameter_meshdatasetgroups(context: ProcessingContext) -> None:
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
    value = inp.value([0, 5, 7], context)
    assert value == [0, 5, 7]
    assert param.checkValueIsAcceptable(value)
    assert QgsProcessingParameterMeshDatasetGroups.valueAsDatasetGroup(value) == [0, 5, 7]

    invalids: tuple[JsonValue, ...] = ([], [-1], ["a"])
    for invalid in invalids:
        with pytest.raises(ValidationError):
            inp.value(invalid, context)

    metadata = {
        md.role: md.value for md in inp.description().metadata if isinstance(md, MetadataValue)
    }
    assert metadata["meshLayerParameterName"] == "Mesh"
    assert sorted(cast("list", metadata["supportedDataTypes"])) == ["DataOnFaces", "DataOnVertices"]


def test_parameter_meshdatasettime() -> None:
    param = QgsProcessingParameterMeshDatasetTime("MeshDatasetTime")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMeshDatasetTime)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_meshdatasetdatetime::", schema)

    # Datetime object are accepted as input value
    value = inp.value({"type": "defined-date-time", "value": datetime.now()})  # type: ignore [dict-item]
    assert param.checkValueIsAcceptable(value)
