from pathlib import Path
from typing import Iterator, cast

import pytest

from pydantic import ValidationError
from qjazz_core.condition import unwrap

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
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
        unwrap(layer.dataProvider()).addFeature(feature)
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
    unwrap(context.temporaryLayerStore()).addMapLayer(points_3857)

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
    unwrap(context.temporaryLayerStore()).addMapLayer(points_3857)

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
    unwrap(context.temporaryLayerStore()).addMapLayer(points_3857)

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
    project = unwrap(QgsProject.instance())
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


#
# Aggregates
#


def _aggregates_param():
    alg = QgsApplication.processingRegistry().algorithmById("native:aggregate")
    assert alg is not None
    return alg.parameterDefinition("AGGREGATES")


def test_parameter_aggregate_metadata(qgis_session: ProcessingConfig):
    """The parent layer is published although the parameter is a generic definition"""
    inp = InputParameter(_aggregates_param())

    metadata = {md.role: md.value for md in inp.description().metadata}  # type: ignore[union-attr]
    assert metadata["parentLayerParameterName"] == "INPUT"


@pytest.mark.parametrize(
    "type_name,type_,sub_type",
    [
        # From QgsFieldMappingModel.supportedDataTypes()
        ("integer", 2, 0),
        ("int8", 4, 0),
        ("double precision", 6, 0),
        ("text", 10, 0),
        ("date", 14, 0),
        ("time", 15, 0),
        ("datetime", 16, 0),
        ("boolean", 1, 0),
        ("binary", 12, 0),
        ("stringlist", 11, 10),
        ("integerlist", 9, 2),
        ("doublelist", 9, 6),
        ("integer64list", 9, 4),
    ],
)
def test_parameter_aggregate_types(
    qgis_session: ProcessingConfig,
    type_name: str,
    type_: int,
    sub_type: int,
):
    """Field type names are translated to QVariant types"""
    param = _aggregates_param()
    value = InputParameter(param).value(
        [{"name": "out", "type": type_name, "input": '"f"', "aggregate": "first_value"}],
    )
    assert value == [
        {
            "name": "out",
            "type": type_,
            "sub_type": sub_type,
            "type_name": type_name,
            "input": '"f"',
            "aggregate": "first_value",
        },
    ]
    assert param.checkValueIsAcceptable(value)


@pytest.mark.parametrize("type_", [6, "6", "double"])
def test_parameter_aggregate_invalid_type(qgis_session: ProcessingConfig, type_: int | str):
    with pytest.raises(ValidationError):
        InputParameter(_aggregates_param()).value(
            [{"name": "out", "type": type_, "input": '"f"', "aggregate": "sum"}],
        )


def test_parameter_aggregate_run(qgis_session: ProcessingConfig):
    """Run the aggregate algorithm with the converted definitions"""
    layer = QgsVectorLayer("Polygon?crs=EPSG:3857&field=label:string", "polygons", "memory")
    for label, wkt in (
        ("a", "POLYGON((0 0,10 0,10 10,0 10,0 0))"),
        ("b", "POLYGON((20 0,30 0,30 10,20 10,20 0))"),
    ):
        feature = QgsFeature(layer.fields())
        feature.setAttribute("label", label)
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        unwrap(layer.dataProvider()).addFeature(feature)

    aggregates = InputParameter(_aggregates_param()).value(
        [
            {"name": "total_area", "type": "double precision", "input": "$area", "aggregate": "sum"},
            {"name": "labels", "type": "text", "input": '"label"', "aggregate": "concatenate"},
            {"name": "count", "type": "integer", "input": '"label"', "aggregate": "count"},
        ],
    )

    context = QgsProcessingContext()
    alg = unwrap(QgsApplication.processingRegistry()).algorithmById("native:aggregate")
    assert alg is not None
    results, ok = alg.run(
        {"INPUT": layer, "GROUP_BY": "NULL", "AGGREGATES": aggregates, "OUTPUT": "memory:"},
        context,
        QgsProcessingFeedback(),
    )
    assert ok

    output = cast("QgsVectorLayer",context.getMapLayer(results["OUTPUT"]))
    assert output is not None
    fields = {f.name(): f.type() for f in output.fields()}  # type: ignore[attr-defined]
    assert fields == {"total_area": 6, "labels": 10, "count": 2}

    feature = next(output.getFeatures())
    assert feature["total_area"] == 200.0
    assert feature["count"] == 2
