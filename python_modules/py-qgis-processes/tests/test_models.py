
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsProcessingOutputLayerDefinition,
)

from py_qgis_processes.processing import (
    InputParameter,
    OutputParameter,
    ProcessingContext,
    utils,
)


def test_model_algorithms(qgis_session, plugins, projects):
    """ Execute algorithm from a model
    """
    registry = QgsApplication.processingRegistry()

    alg = registry.algorithmById('model:centroides')
    assert alg is not None

    project = projects.get('/france/france_parts')

    inputs = {p.name(): InputParameter(p, project) for p in alg.parameterDefinitions()}
    outputs = {d.name(): OutputParameter(d, alg) for d in alg.outputDefinitions()}

    print("\ntest_model_algorithms:inputs\n", {i.name: i.json_schema() for i in inputs.values()})
    print("\ntest_model_algorithms:outputs\n", {i.name: i.json_schema() for i in outputs.values()})

    context = ProcessingContext(qgis_session)
    context.setProject(project)
    context.job_id = "test_model_algorithms"

    values = {
        'input': 'france_parts',
        'native:centroids_1:OUTPUT': 'output_layer',
    }

    # Convert to processing parameters
    parameters = {n: inputs[n].value(v, context) for n, v in values.items()}

    destination_param = parameters['native:centroids_1:OUTPUT']

    # print(
    #    "\ntest_model_algorithms:destination_param",
    #    f"destinationName = {destination_param.destinationName}",
    #    f"sink = {destination_param.sink}",
    # )

    assert isinstance(destination_param, QgsProcessingOutputLayerDefinition)
    assert destination_param.destinationName == 'output_layer'

    # Create a destination project
    destination_project = context.create_project(utils.get_valid_filename(alg.id()))

    print("\ntest_model_algorithms:destination_project:", destination_project.fileName())
    assert Path(destination_project.fileName()).is_relative_to(context.workdir)
