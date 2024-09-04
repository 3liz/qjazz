#
# Processing jobs
#

import subprocess  # nosec
import sys

from celery.signals import worker_process_init, worker_ready
from typing_extensions import (
    Dict,
    List,
    Optional,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.celery import Job, JobContext

from .config import lookup_config_path
from .context import FeedBack, QgisContext
from .schemas import (
    JobExecute,
    JobResults,
    ProcessDescription,
    ProcessSummary,
    ProcessSummaryList,
)
from .worker import (
    QgisJob,
    QgisProcessJob,
    app,
    control_command,
    inspect_command,
)

#
#  Processes cache
#


class ProcessCache:

    Command = (
        f'{sys.executable}',
        '-m',
        'py_qgis_processes.processing',
        '-C',
        f'{lookup_config_path()}',
        'process',
    )

    def __init__(self) -> None:
        self._descriptions: Dict[str, ProcessDescription] = {}
        self._processes: List[ProcessSummary] = []
        self._known_processes: set[str] = set()

    @property
    def processes(self) -> Dict:
        return ProcessSummaryList.dump_python(self._processes, mode='json', exclude_none=True)

    def describe(self, ident: str, project: Optional[str]) -> Dict | None:
        """ Return process description
        """
        if ident not in self._known_processes:
            return None

        key = f'{ident}@{project}'

        description = self._descriptions.get(key)
        if not description:

            logger.info("Getting process description for %s, project=%s", ident, project)

            arguments = [*self.Command, 'describe', ident]
            if project:
                arguments.extend(('--project', project, '--dont-resolve-layers'))

            p = subprocess.run(arguments, capture_output=True)  # nosec
            p.check_returncode()

            description = ProcessDescription.model_validate_json(p.stdout)

            self._descriptions[key] = description

        return description.model_dump(mode='json', exclude_none=True)

    def update(self) -> List[ProcessSummary]:
        """ Update process summary list
        """
        logger.info("Updating processes cache")

        p = subprocess.run([*self.Command, 'list', '--json'], capture_output=True)  # nosec
        p.check_returncode()

        self._processes = ProcessSummaryList.validate_json(p.stdout)
        self._descriptions.clear()

        self._known_processes = {p.id_ for p in self._processes}

        return self._processes


# Enable cache reload command
app.processes_cache = ProcessCache()


#
#  Signals
#

# Called at process initialization
# See https://docs.celeryq.dev/en/stable/userguide/signals.html#worker-process-init


@worker_process_init.connect
def init_qgis(*args, **kwargs):
    """ Initialize Qgis context in each process
    """
    QgisContext.setup_processing(app.processing_config)


@worker_ready.connect
def on_worker_ready(*args, **kwargs):
    app.processes_cache.update()


#
# Control commands
#

@control_command()
def reload_processes_cache(_):
    """ Reload the processes cache
    """
    app.processes_cache.update()


#
# Inspect commands
#
@inspect_command()
def list_processes(_) -> Dict:
    """Return processes list
    """
    return app.processes_cache.processes


@inspect_command(
    args=[('ident', str), ('project_path', str)],
)
def describe_process(_, ident: str, project_path: str | None) -> Dict | None:
    """Return process description
    """
    return app.processes_cache.describe(ident, project_path)

#
# Processing tasks
#


@app.job(name="process_validate", base=QgisJob)
def validate_process_inputs(
    self: Job,
    ctx: JobContext,
    /,
    ident: str,
    request: JobExecute,
    project_path: Optional[str] = None,
):
    """Validate process inputs without executing
    """
    ctx.qgis_context.validate(
        ident,
        request,
        feedback=FeedBack(self.setprogress),
        project_path=project_path,
    )


@app.job(name="process_execute", bind=True, run_context=True, base=QgisProcessJob)
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
    # Optional context attributes
    public_url: str | None
    try:
        public_url = ctx.public_url
    except AttributeError:
        public_url = None

    return ctx.qgis_context.execute(
        ctx.task_id,
        ident,
        request,
        feedback=FeedBack(self.set_progress),
        project_path=project_path,
        public_url=public_url,
    )
