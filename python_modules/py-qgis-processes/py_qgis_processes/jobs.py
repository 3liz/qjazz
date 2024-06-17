#
# Processing worker
#

from time import time

from celery.worker.control import inspect_command
from pydantic import TypeAdapter
from typing_extensions import (
    Dict,
    List,
    Optional,
    Sequence,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import (
    assert_postcondition,
)

from .celery import Job, JobContext, Worker
from .config import load_configuration
from .context import FeedBack, QgisContext
from .processing.prelude import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessDescription,
    ProcessingContext,
    ProcessSummary,
)
from .processing.schemas import LinkHttp

#
# Create worker application
#


class ProcessingWorker(Worker):
    def __init__(self, **kwargs) -> None:
        from kombu import Queue

        conf = load_configuration()

        service_name = conf.worker.service_name

        self.service_name = service_name

        super().__init__(service_name, conf.worker, **kwargs)

        # We want each service with its own queue and exchange
        self.conf.task_default_queue = f"py-qgis.{service_name}"
        self.conf.task_default_exchange = f"py-qgis.{service_name}"

        self.conf.task_default_exchange_type = 'topic'
        self.conf.task_default_routing_key = 'task.default'
        self.conf.task_queues = {
            Queue(f"py-qgis.{service_name}.Tasks", routing_key='task.#'),
            Queue(f"py-qgis.{service_name}.Inventory", routing_key='processes.#'),
        }

        # See https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-worker_prefetch_multiplier
        self.conf.worker_prefetch_multiplier = 1

        self._job_context.update(processing_config=conf.processing)

        self._service_name = service_name
        self._service_title = conf.worker.title
        self._service_description = conf.worker.description
        self._service_links = conf.worker.links

        self._online_since = time()


app = ProcessingWorker()


# Inspect commands

LinkSequence = TypeAdapter(Sequence[LinkHttp])


@inspect_command()
def presence(_) -> Dict:
    from qgis.core import Qgis, QgsCommandLineUtils
    return {
        'service': app._service_name,
        'title': app._service_title,
        'description': app._service_description,
        'links': LinkSequence.dump_python(
            app._service_links,
            mode='json',
            by_alias=True,
            exclude_none=True,
        ),
        'online_since': app._online_since,
        'qgis_version_info': Qgis.versionInt(),
        'versions': QgsCommandLineUtils.allVersions(),
    }


#
# Jobs
#


@app.job(name="process_list", run_context=True)
def list_processes(ctx: JobContext, /) -> List[ProcessSummary]:
    """Return the list of processes
    """
    with QgisContext(ctx):
        algs = ProcessAlgorithm.algorithms(include_deprecated=False)
        return [alg.summary() for alg in algs]


@app.job(name="process_describe", run_context=True)
def describe_process(
    ctx: JobContext,
    /,
    ident: str,
    project_path: Optional[str],
) -> ProcessDescription | None:
    """Return process description
    """
    with QgisContext(ctx) as qgis_context:
        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg:
            project = qgis_context.project(project_path) if project_path else None
            return alg.description(project)
        else:
            return None


@app.job(name="process_validate")
def validate_process_inputs(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
):
    """Validate process inputs

       Validate process inputs without executing
    """
    with QgisContext(ctx) as qgis_context:

        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ValueError(f"Algorithm '{ident}' not found")

        project = qgis_context.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ValueError(f"Algorithm {ident} require project")

        feedback = FeedBack(self.setprogress)
        context = ProcessingContext(qgis_context.processing_config)
        context.setFeedback(feedback)

        if project:
            context.setProject(project)

        alg.validate_execute_parameters(request, feedback, context)


@app.job(name="process_execute", bind=True, run_context=True)
def execute_process(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
) -> JobResults:
    """Execute process
    """

    with QgisContext(ctx) as qgis_context:

        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ValueError(f"Algorithm '{ident}' not found")

        project = qgis_context.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ValueError(f"Algorithm {ident} require project")

        feedback = FeedBack(self.set_progress)
        context = ProcessingContext(qgis_context.processing_config)
        context.setFeedback(feedback)

        context.job_id = ctx.task_id
        context.workdir.mkdir(parents=True, exist_ok=True)

        # Optional context attributes
        try:
            context.public_url = ctx.public_url
        except AttributeError:
            pass

        if project:
            context.setProject(project)

        results = alg.execute(request, feedback, context)

        # Write modified project
        destination_project = context.destination_project
        if destination_project and destination_project.isDirty():
            logger.debug("Writing destination project")
            assert_postcondition(
                destination_project.write(),
                f"Failed no save destination project {destination_project.fileName()}",
            )

        return results
