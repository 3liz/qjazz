
from pathlib import Path

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMeshLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
)

from py_qgis_processes.processing.config import ProcessingConfig
from py_qgis_processes.processing.inputs import InputParameter
from py_qgis_processes.processing.inputs.layers import (
    ParameterFeatureSource,
    ParameterMapLayer,
    ParameterMultipleLayers,
    ParameterRasterLayer,
    ParameterVectorDestination,
    ParameterVectorLayer,
)


def test_parameter_layer_maplayer():

    param = QgsProcessingParameterMapLayer("MapLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterMapLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_maplayer::", schema)

    assert schema['format'] == 'x-qgis-parameter-maplayer'

    # Check layer spec
    value = inp.value("layer:layername")
    assert value == "layername"

    # test arbitrary layer scheme
    value = inp.value("foobar:layername")
    assert value == "foobar:layername"


def test_parameter_layer_vectorlayer():

    param = QgsProcessingParameterVectorLayer("VectorLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterVectorLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectorlayer::", schema)

    assert schema['format'] == 'x-qgis-parameter-vectorlayer'


def test_parameter_layer_rasterlayer():

    param = QgsProcessingParameterRasterLayer("RasterLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterRasterLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_rasterlayer::", schema)

    assert schema['format'] == 'x-qgis-parameter-rasterlayer'


def test_parameter_layer_featuresource(qgis_session):

    param = QgsProcessingParameterFeatureSource("FeatureSource")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterFeatureSource)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_featuresource::", schema)

    assert schema['format'] == 'x-qgis-parameter-featuresource'


def test_parameter_layer_multiplelayers(projects):

    project = projects.get('/france/france_parts')

    param = QgsProcessingParameterMultipleLayers("MultipleLayers")

    inp = InputParameter(param, project)
    assert isinstance(inp, ParameterMultipleLayers)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_multiplelayers::", schema)

    assert schema['format'] == 'x-qgis-parameter-multiplelayers'
    assert 'france_parts' in schema['items']['enum']


def test_parameter_layer_vectordestination(qgis_session: ProcessingConfig):

    param = QgsProcessingParameterVectorDestination("VectorDestination")

    assert qgis_session.default_vector_file_ext == 'fgb'

    assert param.defaultFileExtension() == 'fgb'

    context = QgsProcessingContext()
    context.destination_project = None

    config = qgis_session

    inp = InputParameter(param, config=config)
    assert isinstance(inp, ParameterVectorDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectordestination::schema", schema)

    assert schema['format'] == 'x-qgis-parameter-vectordestination'

    value = inp.value("bar", context)
    assert isinstance(value, QgsProcessingOutputLayerDefinition)
    assert value.destinationName == 'bar'
    assert value.sink.staticValue() == './VectorDestination.fgb'

    config_update = dict(raw_destination_input_sink=True)

    inp.set_config(config.model_copy(update=config_update))

    value = inp.value("/foobar.csv", context)
    assert value.destinationName == 'foobar'
    assert value.sink.staticValue() == 'foobar.csv'

    value = inp.value("/foobar", context)
    assert value.destinationName == 'foobar'
    assert value.sink.staticValue() == 'foobar.fgb'

    config_update.update(raw_destination_root_path=Path('/unsafe'))

    inp.set_config(config.model_copy(update=config_update))
    value = inp.value("file:/path/to/foobar.csv|layername=foobaz", context)
    assert value.destinationName == 'foobaz'
    assert value.sink.staticValue() == '/unsafe/path/to/foobar.csv'

    # Use postgres uri as sink
    value = inp.value("postgres://service=foobar|layername=foobaz")
    assert value.destinationName == 'foobaz'
    assert value.sink.staticValue() == 'postgres://service=foobar'


def test_parameter_layer_mesh():

    param = QgsProcessingParameterMeshLayer("Mesh")

    inp = InputParameter(param)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_mesh::", schema)

    assert schema['format'] == 'x-qgis-parameter-meshlayer'
