
import mimetypes

from pathlib import Path

import pytest

from qgis.core import (
    QgsProcessingOutputLayerDefinition,
    QgsProcessingUtils,
)

from py_qgis_processes.processing.prelude import (
    InputValueError,
    JobExecute,
    ProcessAlgorithm,
    ProcessingContext,
    runalg,
)

from .utils import FeedBack


def test_algorithms_simple(feedback, context, plugins):
    """ Execute a simple algorithm
    """
    pa = ProcessAlgorithm.find_algorithm('processes_test:testsimplevalue')

    print("\ntest_algorithms_simple:description", pa.description().model_dump_json(indent=True))

    request = JobExecute(
        inputs={
            'PARAM1': '1',
            'PARAM2': 'stuff',
        },
    )

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithm_simple:results", results)

    assert results['OUTPUT'] == "1 stuff"


def test_algorithms_option(feedback, context, plugins):
    """ Execute a simple choice algorithm
    """
    pa = ProcessAlgorithm.find_algorithm('processes_test:testoptionvalue')

    print("\ntest_algorithms_option:description", pa.description().model_dump_json(indent=True))

    request = JobExecute(
        inputs={'INPUT': 'value1'},
    )

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithm_option:results", results)

    assert results['OUTPUT'] == "selection is 0"


def test_algorithms_multioption(feedback, context, plugins):
    """ Execute a multiple choice algorithm
    """
    pa = ProcessAlgorithm.find_algorithm('processes_test:testmultioptionvalue')

    print("\ntest_algorithms_multioption::description", pa.description().model_dump_json(indent=True))

    request = JobExecute(
        inputs={'INPUT': ['value1', 'value3']},
    )

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithm_option::results", results)

    assert results['OUTPUT'] == "selection is 0,2"


def test_algorithms_layerdestination(qgis_session, plugins, projects):
    """ Test layer copy: input one layer, output one layer.
        Test layer destination
    """
    feedback = FeedBack()
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    context.job_id = "test_algorithms_layerdestination"
    context.workdir.mkdir(exist_ok=True)

    pa = ProcessAlgorithm.find_algorithm('processes_test:testcopylayer')

    print("\ntest_algorithms_copylayer::description", pa.description().model_dump_json(indent=True))

    # Need a input project
    assert pa.require_project

    request = JobExecute(
        inputs={
            'INPUT': 'france_parts',
            'OUTPUT': 'france_parts_2',  # Destination layer
        },
    )

    # No project set, should raise
    with pytest.raises(InputValueError):
        pa.validate_execute_parameters(request, feedback, context)

    context.setProject(projects.get('/france/france_parts'))

    parameters, _inputs, _outputs = pa.validate_execute_parameters(request, feedback, context)

    assert isinstance(parameters['OUTPUT'], QgsProcessingOutputLayerDefinition)
    assert parameters['OUTPUT'].destinationName == 'france_parts_2'

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithm_copylayer::results", results)

    assert context.destination_project.count() == 1

    layers = context.destination_project.mapLayersByName('france_parts_2')
    assert len(layers) == 1

    layer = layers[0]
    print("\ntest_algorithms_copylayer::dataUrl", layer.dataUrl())

    source = Path(layer.source())
    assert source.is_relative_to(context.workdir)
    assert source.stem == 'OUTPUT'

    # Check output
    out = results['OUTPUT']
    assert out['type'] == 'application/x-ogc-wms'
    assert out['href'] == context.ows_reference(
        service="WMS",
        request="GetCapabilities",
        query="LAYERS=france_parts_2",
    )


def test_algorithms_nativewrapper(qgis_session, plugins, projects):
    """ Test wrapping a native algorithm.
    """
    feedback = FeedBack()
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    context.job_id = "test_algorithms_nativewrapper"
    context.workdir.mkdir(exist_ok=True)

    pa = ProcessAlgorithm.find_algorithm('processes_test:simplebuffer')

    print("\ntest_algorithms_nativewrapper::description", pa.description().model_dump_json(indent=True))

    request = JobExecute(
        inputs={
            'INPUT': 'france_parts',
            'OUTPUT_VECTOR': 'buffer',
            'DISTANCE': 0.05,
        },
    )

    context.setProject(projects.get('/france/france_parts'))

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithm_nativewrapper::results", results)

    # out = results.get('OUTPUT_VECTOR')

    # Get the layer
    srclayer = QgsProcessingUtils.mapLayerFromString('france_parts', context)
    assert srclayer is not None

    layers = context.destination_project.mapLayersByName('buffer')
    assert len(layers) == 1

    output_layer = layers[0]
    assert output_layer.featureCount() == srclayer.featureCount()

    print(
        "\ntest_algorithms_nativewrapper::dataUrl",
        output_layer.dataUrl(),
        output_layer.dataUrlFormat(),
    )

    default_ext = QgsProcessingUtils.defaultVectorExtension()

    assert output_layer.dataUrlFormat() == mimetypes.types_map.get(f".{default_ext}")

    source = Path(output_layer.source())
    assert source.is_relative_to(context.workdir)
    assert source.stem == 'OUTPUT_VECTOR'


def test_algorithms_vectorlayeroutput(qgis_session, plugins, projects):
    """ Test layer output
    """
    feedback = FeedBack()
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    context.job_id = "test_algorithms_layeroutput"
    context.workdir.mkdir(exist_ok=True)

    pa = ProcessAlgorithm.find_algorithm('processes_test:vectoroutput')

    print("\ntest_algorithms_vectorlayeroutput::description", pa.description().model_dump_json(indent=True))

    request = JobExecute(
        inputs={
            'INPUT': 'france_parts',
            'DISTANCE': 0.05,
        },
        outputs={
            'OUTPUT': {'format': {'mediaType': 'application/x-ogc-wfs'}},
        },
    )

    context.setProject(projects.get('/france/france_parts'))

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithms_vectorlayeroutput::results", results)

    assert context.destination_project.count() == 1

    out = results.get('OUTPUT')
    assert out['type'] == "application/x-ogc-wfs"


def test_algorithms_selectfeatures(qgis_session, plugins, projects):
    """ Test layer output
    """
    feedback = FeedBack()
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    context.job_id = "test_algorithms_selectfeatures"
    context.workdir.mkdir(exist_ok=True)

    pa = ProcessAlgorithm.find_algorithm('processes_test:simplebuffer')

    request = JobExecute(
        inputs={
            'INPUT': {
                'source': 'france_parts',
                'expression': 'OBJECTID=2662 OR OBJECTID=2664',
            },
            'OUTPUT_VECTOR': 'buffer',
            'DISTANCE': 0.05,
        },
    )

    context.setProject(projects.get('/france/france_parts'))

    results = pa.execute(request, feedback, context)
    print("\ntest_algorithms_selectfeatures::results", results)

    layers = context.destination_project.mapLayersByName('buffer')
    assert len(layers) == 1

    output_layer = layers[0]
    assert output_layer.featureCount() == 2


def test_algorithms_exception(qgis_session, plugins, projects):
    """ Test Error in algorithm
    """
    feedback = FeedBack()
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    context.job_id = "test_algorithms_selectfeatures"
    context.workdir.mkdir(exist_ok=True)

    pa = ProcessAlgorithm.find_algorithm('processes_test:testraiseerror')

    request = JobExecute(inputs={'PARAM1': 20})

    with pytest.raises(runalg.RunProcessingException):
        _ = pa.execute(request, feedback, context)
