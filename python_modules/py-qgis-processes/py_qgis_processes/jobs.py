#
# Processing worker
#
import os
import sys

from pathlib import Path
from uuid import uuid4

from typing_extensions import (
    List,
    Optional,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.condition import (
    assert_postcondition,
    assert_precondition,
)
from py_qgis_contrib.core.qgis import (
    show_all_versions,
)
from py_qgis_processes_schemas import (
    InputValueError,
    JsonDict,
)

from .celery import Job, JobContext, Worker
from .context import FeedBack, QgisContext
from .processing import (
    JobExecute,
    JobResults,
    ProcessAlgorithm,
    ProcessingContext,
    ProcessSummary,
    runalg,
)


class ProcessingWorker(Worker):
    def __init__(self, **kwargs):

        conf = load_configuration()
        super().__init__(conf.worker, **kwargs)

        self._job_context.update(processing_config=conf.processing)

#
# Create worker application
#


app = ProcessingWorker()


#
# Jobs
#


@app.job(name="versions", run_context=True)
def env(ctx: JobContext, /) -> JsonDict:
    from qgis.core import Qgis
    return dict(
        qgis_version_info=Qgis.versionInt(),
        versions=list(show_all_versions()),
    )


@app.job(name="process_list", run_context=True)
def list_processes(ctx: JobContext, /) -> List[ProcessSummary]:
    """Return the list of processes
    """
    with QgisContext(ctx):
        algs = ProcessAlgorithm.algorithms(include_deprecated=False)
        return [alg.summary() for alg in algs]


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
            raise ValueError("Algorithm {ident} require project")

        feedback = FeedBack(self.setprogress)
        context = ProcessingContext(qgis_context.processing_config)
        context.setFeedback(feedback)
        context.store_url(ctx.store_url)
        context.advertised_services_url(ctx.advertised_services_url)

        if project:
            context.setProject(project)

        try:
            alg.validate_execute_parameters(request, feedback, context)
        except InputValueError as err:
            raise ValueError(f"Input error: {err}, {err.json}") from None


@app.job(name="process_execute", bind=True, run_context=True)
def execute_process(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
) -> JobResults:
    """Return the list of processes
    """
    with QgisContext(ctx) as qgis_context:

        alg = ProcessAlgorithm.find_algorithm(ident)
        if alg is None:
            raise ValueError(f"Algorithm '{ident}' not found")

        project = qgis_context.project(project_path) if project_path else None
        if not project and alg.require_project:
            raise ValueError("Algorithm {ident} require project")

        feedback = FeedBack(self.setprogress)
        context = ProcessingContext(qgis_context.processing_config)
        context.setFeedback(feedback)

        context.job_id = str(uuid4())
        context.workdir.mkdir(parents=True, exist_ok=True)
        context.store_url(ctx.store_url)
        context.advertised_services_url(ctx.advertised_services_url)

        if project:
            context.setProject(project)
        elif alg.require_project:
            raise ValueError(f"{ident} require project")

        try:
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

        except InputValueError as err:
            raise ValueError(f"Input error: {err}, {err.json}") from None
        except runalg.RunProcessingException as err:
            raise ValueError(f"Execute error: {err}") from None


#
# Configuration helpers
#

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
