
from pathlib import Path

from qgis.core import (
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterAlignRasterLayers,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFieldMapping,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterTinInputLayers,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
    QgsProcessingUtils,
)

from py_qgis_processes.processing.config import ProcessingConfig
from py_qgis_processes.processing.context import ProcessingContext
from py_qgis_processes.processing.inputs import InputParameter
from py_qgis_processes.processing.inputs.layers import (
    FieldParameterDataType,
    ParameterAlignRasterLayers,
    ParameterFeatureSource,
    ParameterField,
    ParameterFieldMapping,
    ParameterMapLayer,
    ParameterMultipleLayers,
    ParameterRasterDestination,
    ParameterRasterLayer,
    ParameterTinInputLayers,
    ParameterVectorDestination,
    ParameterVectorLayer,
)


def meta(seq, s):
    return next(filter(lambda m: m.role == s, seq)).value


def test_parameter_layer_maplayer():

    param = QgsProcessingParameterMapLayer("MapLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterMapLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_maplayer::", schema)


def test_parameter_layer_vectorlayer():

    param = QgsProcessingParameterVectorLayer("VectorLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterVectorLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectorlayer::", schema)


def test_parameter_layer_rasterlayer():

    param = QgsProcessingParameterRasterLayer("RasterLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterRasterLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_rasterlayer::", schema)


def test_parameter_layer_featuresource(qgis_session):

    param = QgsProcessingParameterFeatureSource("FeatureSource")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterFeatureSource)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_featuresource::", schema)

    assert schema.get('format') == 'x-feature-source'


def test_parameter_layer_multilayers(projects):

    project = projects.get('/france/france_parts')

    param = QgsProcessingParameterMultipleLayers("MultipleLayers")

    inp = InputParameter(param, project)
    assert isinstance(inp, ParameterMultipleLayers)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_multiplelayers::", schema)

    assert 'france_parts' in schema['items']['enum']


def test_parameter_layer_vectordestination(qgis_session: ProcessingConfig):

    param = QgsProcessingParameterVectorDestination("VectorDestination")

    assert QgsProcessingUtils.defaultVectorExtension()  == qgis_session.default_vector_file_ext
    assert param.defaultFileExtension() == qgis_session.default_vector_file_ext

    config = qgis_session

    context = ProcessingContext(config)
    assert context.destination_project is None

    workdir = context.workdir

    inp = InputParameter(param)
    assert isinstance(inp, ParameterVectorDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectordestination::schema", schema)

    assert schema.get('default') is None

    value = inp.value("bar", context)
    assert isinstance(value, QgsProcessingOutputLayerDefinition)
    assert value.destinationName == 'bar'
    assert value.sink.staticValue() == str(workdir.joinpath('VectorDestination.fgb'))

    context = ProcessingContext(
        config.model_copy(
            update=dict(raw_destination_input_sink=True),
        ),
    )

    value = inp.value("/foobar.csv", context)
    assert value.destinationName == 'foobar'
    assert value.sink.staticValue() == 'foobar.csv'

    value = inp.value("/foobar", context)
    assert value.destinationName == 'foobar'
    assert value.sink.staticValue() == 'foobar.fgb'

    context = ProcessingContext(
        config.model_copy(
            update=dict(
                raw_destination_input_sink=True,
                raw_destination_root_path=Path('/unsafe'),
            ),
        ),
    )

    value = inp.value("file:/path/to/foobar.csv|layername=foobaz", context)
    assert value.destinationName == 'foobaz'
    assert value.sink.staticValue() == '/unsafe/path/to/foobar.csv'

    # Use postgres uri as sink
    value = inp.value("postgres://service=foobar|layername=foobaz", context)
    assert value.destinationName == 'foobaz'
    assert value.sink.staticValue() == 'postgres://service=foobar'


def test_parameter_layer_rasterdestination(qgis_session: ProcessingConfig):

    param = QgsProcessingParameterRasterDestination("RasterDestination")
    config = qgis_session

    context = ProcessingContext(config)
    context.destination_project = None

    inp = InputParameter(param)
    assert isinstance(inp, ParameterRasterDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_rasterdestination::schema", schema)


def test_parameter_tininputlayers():

    param = QgsProcessingParameterTinInputLayers("TinInputLayers")

    inp = InputParameter(param)

    assert isinstance(inp, ParameterTinInputLayers)

    schema = inp.json_schema()
    print("\ntest_parameter_tininputlayer::", schema)


def test_parameter_field():

    param = QgsProcessingParameterField(
        "Field",
        parentLayerParameterName="ParentLayer",
        type=FieldParameterDataType.Numeric,
    )

    inp = InputParameter(param)
    assert isinstance(inp, ParameterField)

    schema = inp.json_schema()
    print("\ntest_parameter_field::", schema)
    assert schema['type'] == 'string'

    md = inp.metadata(param)
    print("test_parameter_field::metadata", md)
    assert meta(md, "typeName") == "field"
    assert meta(md, "parentLayerParameterName") == "ParentLayer"
    assert meta(md, "dataType") == "Numeric"

    param = QgsProcessingParameterField("Field", allowMultiple=True)
    inp = InputParameter(param)
    schema = inp.json_schema()
    print("\ntest_parameter_field::multiple", schema)
    assert schema['type'] == 'array'
    assert schema['minItems'] == 1


def test_parameter_fieldmapping():

    param = QgsProcessingParameterFieldMapping(
        "FieldMapping",
        parentLayerParameterName="ParentLayer",
    )

    inp = InputParameter(param)

    assert isinstance(inp, ParameterFieldMapping)

    schema = inp.json_schema()
    print("\ntest_parameter_fieldmapping::", schema)


def test_parameter_alignrasterlayers(projects):

    project = projects.get('/samples/raster_layer')

    param = QgsProcessingParameterAlignRasterLayers("AlignRasterLayers")

    inp = InputParameter(param, project)

    assert isinstance(inp, ParameterAlignRasterLayers)

    schema = inp.json_schema()
    print("\ntest_parameter_alignrasterlayers::", schema)

    value = inp.value(
        [
            {
                "inputFile": "raster_layer",
                "outputFile": "whatever",
                "resampleMethod": 0,
            },
        ],
    )

    print("\ntest_parameter_alignrasterlayers::value", value)

    assert param.checkValueIsAcceptable(value)
