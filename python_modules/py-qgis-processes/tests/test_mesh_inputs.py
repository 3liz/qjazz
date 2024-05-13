
from datetime import datetime

from qgis.core import (
    QgsProcessingParameterMeshDatasetGroups,
    QgsProcessingParameterMeshDatasetTime,
    QgsProcessingParameterMeshLayer,
)

from py_qgis_processes.processing.inputs import (
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

    param = QgsProcessingParameterMeshDatasetGroups("MeshDatasetGroups")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMeshDatasetGroups)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_meshdatasetgroups::", schema)


def test_parameter_meshdatasettime():

    param = QgsProcessingParameterMeshDatasetTime("MeshDatasetTime")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterMeshDatasetTime)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_meshdatasetdatetime::", schema)

    value = inp.value({'type': 'defined-date-time', 'value': datetime.now()})
    assert param.checkValueIsAcceptable(value)
