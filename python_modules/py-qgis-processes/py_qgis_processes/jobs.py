#
# Processing worker
#
import os
import sys

from pathlib import Path
from time import time
from uuid import uuid4

from celery.worker.control import inspect_command
from pydantic import Field
from typing_extensions import (
    Dict,
    List,
    Optional,
    cast,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.condition import (
    assert_postcondition,
    assert_precondition,
)

from .celery import CeleryConfig, Job, JobContext, Worker
from .context import FeedBack, QgisContext
from .processing import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessDescription,
    ProcessingConfig,
    ProcessingContext,
    ProcessSummary,
)


def lookup_config_path() -> Path:
    """ Determine config path location
    """
    var = os.getenv('PY_QGIS_PROCESSES_WORKER_CONFIG')
    if var:
        # Path defined with environment MUST exists
        p = Path(var).expanduser()
        assert_precondition(p.exists(), f"File not found {p}")
    else:
        # Search in standards paths
        for search in (
            '/etc/py-qgis-processes/worker.toml',
            '~/.py-qgis-processes/worker.toml',
            '~/.config/py-qgis-processes/worker.toml',
        ):
            p = Path(search).expanduser()
            if p.exists():
                break
        else:
            raise RuntimeError("No configuration found")

    print("=Reading configuration from:", p, file=sys.stderr, flush=True)  # noqa T201
    return p


def load_configuration() -> config.Config:
    """ Load worker configuration
    """
    configpath = lookup_config_path()
    cnf = config.read_config_toml(
        configpath,
        location=str(configpath.parent.absolute()),
    )
    config.confservice.validate(cnf)

    conf = config.confservice.conf
    logger.setup_log_handler(conf.logging.level)
    return conf


#
# Create worker application
#

@config.section('worker', field=...)
class WorkerConfig(CeleryConfig):
    service_name: str = Field(
        title="Name of the service",
        description=(
            "Name used as location service name\n"
            "for initializing Celery worker."
        ),
    )

    title: str = Field(default="", title="Service title")
    description: str = Field(default="", title="Service description")


# Allow type validation
class ConfigProto:
    processing: ProcessingConfig
    worker: WorkerConfig


class ProcessingWorker(Worker):
    def __init__(self, **kwargs) -> None:
        from kombu import Queue

        conf = cast(ConfigProto, load_configuration())

        service_name = conf.worker.service_name
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

        self._job_context.update(processing_config=conf.processing)
        self._service_name = service_name
        self._online_at = time()


app = ProcessingWorker()


# Inspect commands


@inspect_command()
def presence(_) -> Dict:
    from qgis.core import Qgis, QgsCommandLineUtils
    return {
        'service': app._service_name,
        'online_at': app._online_at,
        'qgis_version_info': Qgis.versionInt(),
        'versions': QgsCommandLineUtils.allVersions(),
    }


@inspect_command()
def uptime(_) -> float:
    return app._online_at

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
        context.store_url(ctx.store_url)
        context.advertised_services_url(ctx.advertised_services_url)

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

        context.job_id = str(uuid4())
        context.workdir.mkdir(parents=True, exist_ok=True)

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
