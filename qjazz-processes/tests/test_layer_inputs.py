from pathlib import Path
from typing import Iterator

import pytest

from pydantic import ValidationError

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingOutputLayerDefinition,
    QgsProcessingParameterAlignRasterLayers,
    QgsProcessingParameterDxfLayers,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFieldMapping,
    QgsProcessingParameterMapLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameters,
    QgsProcessingParameterTinInputLayers,
    QgsProcessingParameterVectorDestination,
    QgsProcessingParameterVectorLayer,
    QgsProcessingUtils,
    QgsProject,
    QgsVectorLayer,
)

from qjazz_processes.processing.config import ProcessingConfig
from qjazz_processes.processing.context import ProcessingContext
from qjazz_processes.processing.inputs import InputParameter
from qjazz_processes.processing.inputs.layers import (
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
from qjazz_processes.schemas import InputValueError


def meta(seq, s):
    return next(filter(lambda m: m.role == s, seq)).value


def test_parameter_layer_maplayer():
    param = QgsProcessingParameterMapLayer("MapLayer")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterMapLayer)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_maplayer::", schema)


def test_parameter_layer_vectorlayer(projects):
    project = projects.get("/france/france_parts")

    param = QgsProcessingParameterVectorLayer("VectorLayer")

    inp = InputParameter(param, project)
    assert isinstance(inp, ParameterVectorLayer)
    assert len(list(ParameterVectorLayer.compatible_layers(param, project))) > 0

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectorlayer::", schema)

    assert "france_parts" in schema["enum"]


def test_parameter_layer_rasterlayer(projects):
    project = projects.get("/samples/raster_layer")

    param = QgsProcessingParameterRasterLayer("RasterLayer")

    inp = InputParameter(param, project)
    assert isinstance(inp, ParameterRasterLayer)
    assert len(list(ParameterRasterLayer.compatible_layers(param, project))) > 0

    schema = inp.json_schema()
    print("\ntest_parameter_layer_rasterlayer::", schema)

    # XXX: const is used on literals when there is only a single
    # value
    assert schema["const"] == "raster_layer"


def test_parameter_layer_featuresource(qgis_session):
    param = QgsProcessingParameterFeatureSource("FeatureSource")

    inp = InputParameter(param)
    assert isinstance(inp, ParameterFeatureSource)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_featuresource::", schema)

    assert schema.get("format") == "x-feature-source"


@pytest.fixture()
def points_3857() -> QgsVectorLayer:
    """Memory layer in EPSG:3857 with a point at Paris (fid 1) and at (0, 0) (fid 2)"""
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "points", "memory")
    for x, y in ((261845.7, 6250566.7), (0.0, 0.0)):
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        layer.dataProvider().addFeature(feature)
    return layer


@pytest.mark.parametrize(
    "intersect,expected",
    [
        # CRS84 (default crs without project), reprojected to the layer crs
        ({"bbox": [2, 48, 3, 49]}, [1]),
        # 3D extent
        ({"bbox": [2, 48, 0, 3, 49, 100]}, [1]),
        # Layer crs
        ({"bbox": [-10, -10, 10, 10], "crs": "EPSG:3857"}, [2]),
        ({"bbox": [-10, -10, 10, 10], "crs": "http://www.opengis.net/def/crs/EPSG/0/3857"}, [2]),
    ],
)
def test_parameter_layer_featuresource_intersect(
    qgis_session: ProcessingConfig,
    points_3857: QgsVectorLayer,
    intersect: dict,
    expected: list[int],
):
    context = ProcessingContext(qgis_session)
    context.temporaryLayerStore().addMapLayer(points_3857)

    inp = InputParameter(QgsProcessingParameterFeatureSource("FeatureSource"))
    value = inp.value({"source": points_3857.id(), "intersect": intersect}, context)

    assert value.selectedFeaturesOnly
    assert sorted(points_3857.selectedFeatureIds()) == expected


def test_parameter_layer_featuresource_input_forms(
    qgis_session: ProcessingConfig,
    points_3857: QgsVectorLayer,
):
    """Feature sources are passed as objects"""
    context = ProcessingContext(qgis_session)
    context.temporaryLayerStore().addMapLayer(points_3857)

    inp = InputParameter(QgsProcessingParameterFeatureSource("FeatureSource"))

    # No selection
    value = inp.value({"source": points_3857.id()}, context)
    assert value.source.staticValue() == points_3857.id()
    assert not value.selectedFeaturesOnly

    # Bare layer names are not accepted
    with pytest.raises(ValidationError):
        inp.value(points_3857.id(), context)


def test_parameter_layer_featuresource_intersect_invalid_crs(
    qgis_session: ProcessingConfig,
    points_3857: QgsVectorLayer,
):
    context = ProcessingContext(qgis_session)
    context.temporaryLayerStore().addMapLayer(points_3857)

    inp = InputParameter(QgsProcessingParameterFeatureSource("FeatureSource"))
    with pytest.raises(InputValueError, match="Invalid intersect crs"):
        inp.value(
            {"source": points_3857.id(), "intersect": {"bbox": [0, 0, 1, 1], "crs": "foo"}},
            context,
        )


def test_parameter_layer_multilayers(projects):
    project = projects.get("/france/france_parts")

    param = QgsProcessingParameterMultipleLayers("MultipleLayers")

    inp = InputParameter(param, project)
    assert isinstance(inp, ParameterMultipleLayers)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_multiplelayers::", schema)

    assert "france_parts" in schema["items"]["enum"]


def test_parameter_layer_vectordestination(qgis_session: ProcessingConfig):
    param = QgsProcessingParameterVectorDestination("VectorDestination")

    assert QgsProcessingUtils.defaultVectorExtension() == qgis_session.default_vector_file_ext
    assert param.defaultFileExtension() == qgis_session.default_vector_file_ext

    config = qgis_session

    context = ProcessingContext(config)
    assert context.destination_project is None

    workdir = context.workdir

    inp = InputParameter(param)
    assert isinstance(inp, ParameterVectorDestination)

    schema = inp.json_schema()
    print("\ntest_parameter_layer_vectordestination::schema", schema)

    assert schema.get("default") is None

    value = inp.value("bar", context)
    assert isinstance(value, QgsProcessingOutputLayerDefinition)
    assert value.destinationName == "bar"
    assert value.sink.staticValue() == str(workdir.joinpath("VectorDestination.fgb"))

    context = ProcessingContext(
        config.model_copy(
            update={"raw_destination_input_sink": True},
        ),
    )

    # No root path: absolute paths are stored in the job folder
    value = inp.value("/foobar.csv", context)
    assert value.destinationName == "foobar"
    assert value.sink.staticValue() == str(context.workdir.joinpath("foobar.csv"))

    value = inp.value("/foobar", context)
    assert value.destinationName == "foobar"
    assert value.sink.staticValue() == str(context.workdir.joinpath("foobar.fgb"))

    # Escaping the job folder is not allowed
    with pytest.raises(InputValueError):
        inp.value("/../../foobar.csv", context)
    with pytest.raises(InputValueError):
        inp.value("../foobar.csv", context)

    context = ProcessingContext(
        config.model_copy(
            update={
                "raw_destination_input_sink": True,
                "raw_destination_root_path": Path("/unsafe"),
            },
        ),
    )

    value = inp.value("file:/path/to/foobar.csv|layername=foobaz", context)
    assert value.destinationName == "foobaz"
    assert value.sink.staticValue() == "/unsafe/path/to/foobar.csv"

    # '..' segments are normalized
    value = inp.value("/path/../foobar.csv", context)
    assert value.sink.staticValue() == "/unsafe/foobar.csv"

    # Escaping the root folder is not allowed
    with pytest.raises(InputValueError):
        inp.value("/../etc/foobar.csv", context)
    with pytest.raises(InputValueError):
        inp.value("file:/path/../../../etc/foobar.csv", context)

    # Use postgres uri as sink
    value = inp.value("postgres://service=foobar|layername=foobaz", context)
    assert value.destinationName == "foobaz"
    assert value.sink.staticValue() == "postgres://service=foobar"


def _output_definition(sink: str, name: str = "") -> QgsProcessingOutputLayerDefinition:
    defval = QgsProcessingOutputLayerDefinition(sink)
    defval.destinationName = name
    return defval


@pytest.mark.parametrize(
    "defval,expected_default,expected_ext",
    [
        # Non-file sinks
        (_output_definition("memory:"), None, None),
        (_output_definition("memory:", "mylayer"), "mylayer", None),
        (_output_definition("ogr:dbname='/data/out.gpkg' table=\"out\""), None, None),
        # File sink
        (_output_definition("/data/out.csv"), "out", ".csv"),
        (_output_definition("/data/out.csv|layername=foo", "foo"), "foo", ".csv"),
        # Layer name
        ("mylayer", "mylayer", None),
    ],
)
def test_parameter_layer_destination_defaults(
    qgis_session: ProcessingConfig,
    defval: str | QgsProcessingOutputLayerDefinition,
    expected_default: str | None,
    expected_ext: str | None,
):
    param = QgsProcessingParameterVectorDestination("VectorDestination", defaultValue=defval)

    inp = InputParameter(param)
    assert isinstance(inp, ParameterVectorDestination)

    assert inp.json_schema().get("default") == expected_default
    assert inp.output_extension == (expected_ext or f".{param.defaultFileExtension()}")

    # Non-file default sinks are ignored: the output
    # is always a file in the job folder
    context = ProcessingContext(qgis_session)
    value = inp.value("bar", context)
    assert value.destinationName == "bar"
    assert value.sink.staticValue() == str(
        context.workdir.joinpath(f"VectorDestination{inp.output_extension}"),
    )


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
        type=Qgis.ProcessingFieldParameterDataType.Numeric,
    )

    inp = InputParameter(param)
    assert isinstance(inp, ParameterField)

    schema = inp.json_schema()
    print("\ntest_parameter_field::", schema)
    assert schema["type"] == "string"

    md = inp.metadata(param)
    print("test_parameter_field::metadata", md)
    assert meta(md, "typeName") == "field"
    assert meta(md, "parentLayerParameterName") == "ParentLayer"
    assert meta(md, "dataType") == "Numeric"

    param = QgsProcessingParameterField("Field", allowMultiple=True)
    inp = InputParameter(param)
    schema = inp.json_schema()
    print("\ntest_parameter_field::multiple", schema)
    assert schema["type"] == "array"
    assert schema["minItems"] == 1


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
    project = projects.get("/samples/raster_layer")

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


#
# Multiple layers values
#


@pytest.fixture()
def project_ab() -> Iterator[QgsProject]:
    """Project with two vector layers 'a' and 'b'"""
    # Use the global project instance: a project created from python
    # may be destroyed after QGIS exits (i.e held by a test traceback)
    project = QgsProject.instance()
    project.addMapLayers(
        [
            QgsVectorLayer("Point?crs=EPSG:4326", "a", "memory"),
            QgsVectorLayer("Point?crs=EPSG:4326", "b", "memory"),
        ],
    )
    yield project
    project.removeAllMapLayers()


def _context(config: ProcessingConfig, project: QgsProject) -> ProcessingContext:
    context = ProcessingContext(config)
    context.setProject(project)
    return context


def test_parameter_multiplelayers_value(qgis_session: ProcessingConfig, project_ab: QgsProject):
    """Multiple layers are passed to QGIS as a list"""
    param = QgsProcessingParameterMultipleLayers(
        "Layers",
        layerType=Qgis.ProcessingSourceType.VectorAnyGeometry,
    )
    context = _context(qgis_session, project_ab)

    value = InputParameter(param, project_ab).value(["a", "b"], context)
    assert isinstance(value, list)
    assert sorted(value) == ["a", "b"]

    assert param.checkValueIsAcceptable(value, context)
    layers = QgsProcessingParameters.parameterAsLayerList(param, {"Layers": value}, context)
    assert sorted(layer.name() for layer in layers) == ["a", "b"]


def test_parameter_dxflayers_value(qgis_session: ProcessingConfig, project_ab: QgsProject):
    """Dxf layers are passed to QGIS as a list"""
    param = QgsProcessingParameterDxfLayers("Layers")
    context = _context(qgis_session, project_ab)

    value = InputParameter(param, project_ab).value(["a", "b"], context)
    assert isinstance(value, list)
    assert sorted(value) == ["a", "b"]

    assert param.checkValueIsAcceptable(value, context)


def test_parameter_tininputlayers_value(qgis_session: ProcessingConfig, project_ab: QgsProject):
    """Each Tin input has a single layer source"""
    param = QgsProcessingParameterTinInputLayers("Layers")
    context = _context(qgis_session, project_ab)

    value = InputParameter(param, project_ab).value(
        [{"source": "a", "type": "0", "attributeIndex": "-1"}],
        context,
    )
    assert value == [{"source": "a", "type": "0", "attributeIndex": "-1"}]

    assert param.checkValueIsAcceptable(value, context)
