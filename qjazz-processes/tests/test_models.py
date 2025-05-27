from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsProcessingOutputLayerDefinition,
)

from qjazz_processes.processing.prelude import (
    InputParameter,
    OutputParameter,
    ProcessingContext,
    runalg,
)

from .utils import Feedback


def test_model_algorithms(qgis_session, plugins, projects):
    """Execute algorithm from a model"""
    registry = QgsApplication.processingRegistry()

    alg = registry.algorithmById("model:centroides")
    assert alg is not None

    project = projects.get("/france/france_parts")

    inputs = tuple(InputParameter(p, project) for p in alg.parameterDefinitions())
    outputs = tuple(OutputParameter(p, alg) for p in alg.outputDefinitions())

    print("\ntest_model_algorithms:inputs\n", {i.name: i.json_schema() for i in inputs})
    print("\ntest_model_algorithms:outputs\n", {o.name: o.json_schema() for o in outputs})

    context = ProcessingContext(qgis_session)
    context.setProject(project)
    context.job_id = "test_model_algorithms"

    context.workdir.mkdir(exist_ok=True)

    values = {
        "input": "france_parts",
        "native:centroids_1:OUTPUT": "output_layer",
    }
    # Convert to processing parameters
    parameters = InputParameter.parameters(inputs, values, context)
    print("\ntest_model_algorithms:parameters:", parameters)

    destination_param = parameters["native:centroids_1:OUTPUT"]

    # print(
    #    "\ntest_model_algorithms:destination_param",
    #    f"destinationName = {destination_param.destinationName}",
    #    f"sink = {destination_param.sink}",
    # )

    assert isinstance(destination_param, QgsProcessingOutputLayerDefinition)
    assert destination_param.destinationName == "output_layer"

    # Create a destination project
    destination_project = context.create_project(alg.id())

    print("\ntest_model_algorithms:destination_project:", destination_project.fileName())
    assert Path(destination_project.fileName()).is_relative_to(context.workdir)

    # Set the destination project
    context.destination_project = destination_project

    feedback = Feedback()
    context.feedback = feedback

    # Run algorithm
    results = runalg.execute(alg, parameters, feedback, context)
    print("\ntest_model_algorithms:results:", results)

    # Handle results
    for out in outputs:
        value = results[out.name]
        output = out.output(value, context)
        print(f"\ntest_model_algorithms:output[{out.name}]", output)

    # Process layer outputs
    runalg.process_layer_outputs(alg, context, feedback, context.workdir, destination_project)

    assert destination_project.count() == 1
    layer = destination_project.mapLayersByName(destination_param.destinationName)
    assert layer is not None
