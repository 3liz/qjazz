
import asyncio

from time import time

from celery.result import AsyncResult
from pydantic import Field, JsonValue
from typing_extensions import (
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import Config as BaseConfig
from py_qgis_contrib.core.utils import to_utc_datetime, utc_now
from py_qgis_processes_schemas import (
    InputValueError,  # noqa: F401
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    JsonModel,
    ProcessDescription,
    ProcessSummary,
    ProcessSummaryList,
    RunProcessingException,  # noqa: F401
)

from . import registry
from .celery import Celery, CeleryConfig


class ExecutorConfig(BaseConfig):
    celery: CeleryConfig = CeleryConfig()

    message_expiration_timeout: int = Field(
        default=600,
        title="Message expiration timeout",
        description=(
            "The amount of time an execution message"
            "can wait on queue before beeing processed."
        ),
    )
    task_routes: Dict[str, JsonValue] = Field(
        default={},
        title="Task routes",
        description=(
            "Task routes configuration;\n"
            "follows the Celery automatic routing configuration syntax:\n"
            "https://docs.celeryq.dev/en/stable/userguide/routing.html."
        ),
    )


class PresenceDetails(JsonModel):
    service: str
    online_at: float
    qgis_version_info: int
    versions: str


ServiceDict = Dict[str, Tuple[Sequence[str], PresenceDetails]]


class Executor:

    def __init__(self, conf: Optional[ExecutorConfig] = None, *, name: Optional[str] = None):
        conf = conf or ExecutorConfig()
        self._celery = Celery(name, conf.celery)
        self._services: ServiceDict = {}
        self._expiration_timeout = conf.message_expiration_timeout
        self._result_expires = conf.celery.result_expires

        if conf.task_routes:
            self._celery.conf.task_routes = conf.task_routes

    def presences(self, destinations: Optional[Sequence[str]] = None) -> Dict[str, PresenceDetails]:
        """ Return presence info for online workers
        """
        data = self._celery.control.broadcast(
            'presence',
            reply=True,
            destination=destinations,
        )

        return {k: PresenceDetails.model_validate(v) for row in data for k, v in row.items()}

    @property
    def services(self) -> ServiceDict:
        return self._services

    def get_services(self) -> ServiceDict:
        # Return services destinations (blocking)
        presences = self.presences()
        services: ServiceDict = {}
        for dest, pr in presences.items():
            dests, _ = services.setdefault(pr.service, ([], pr))
            cast(list, dests).append(dest)
        return {k: (tuple(dests), pr) for k, (dests, pr) in services.items()}

    async def update_services(self) -> ServiceDict:
        """ Update services destinations

            Collapse presence details under unique service
            name.
        """
        self._services = await asyncio.to_thread(self.get_services)
        return self._services

    @classmethod
    def get_destinations(cls, service: str, services: ServiceDict) -> Optional[Sequence[str]]:
        item = services.get(service)
        return item and item[0]

    def destinations(self, service: str) -> Optional[Sequence[str]]:
        return self.get_destinations(service, self._services)

    def _processes(
        self,
        service: str,
        timeout: Optional[float] = None,
    ) -> Sequence[ProcessSummary]:
        # List processes for service (blocking version)
        res = self._celery.send_task(
            f"{service}.process_list",
            priority=100,
            queue=f'py-qgis.{service}.Inventory',
            routing_key='processes.list',
            expires=timeout,
        )

        try:
            return ProcessSummaryList.validate_python(res.get(timeout=timeout))
        finally:
            res.forget()

    def _describe(
        self,
        service: str,
        ident: str,
        project: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[ProcessDescription]:
        # Retrieve process description (blocking version)
        res = self._celery.send_task(
            f"{service}.process_describe",
            priority=100,
            queue=f'py-qgis.{service}.Inventory',
            routing_key='processes.describe',
            expires=timeout,
            kwargs={
                '__run_config__':  {
                    'ident': ident,
                    'project_path': project,
                },
            },
        )

        try:
            body = res.get(timeout=timeout)
            return body and ProcessDescription.model_validate(body)
        finally:
            res.forget()

    async def describe(
        self,
        service: str,
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[ProcessDescription]:
        """ Return process description
        """
        return await asyncio.to_thread(
            self._describe,
            service,
            ident,
            project,
            timeout,
        )

    async def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """ Return process description summary
        """
        return await asyncio.to_thread(
            self._processes,
            service,
            timeout,
        )

    def _execute(
        self,
        service: str,
        task: str,
        run_config: Dict[str, JsonValue],
        *,
        expiration_timeout: int,
        context: Optional[JsonDict] = None,
        meta: Optional[Mapping[str, JsonValue]] = None,
        priority: int = 0,
    ) -> AsyncResult:
        # Execute process (blocking)

        meta = meta or {}
        context = context or {}

        return self._celery.send_task(
            f"{service}.{task}",
            priority=priority,
            queue=f'py-qgis.{service}.Tasks',
            routing_key="task.execute",
            expires=expiration_timeout,
            kwargs={
                '__meta__': meta,
                '__context__': context,
                '__run_config__':  run_config,
            },
        )

    async def execute(
        self,
        service: str,
        ident: str,
        request: JobExecute,
        *,
        project: Optional[str] = None,
        context: Optional[JsonDict] = None,
        realm: Optional[str] = None,
    ) -> AsyncResult:
        """ Send an execute request

            Returns the job status.
        """
        created = utc_now()
        meta = {
            'created': created.isoformat(timespec="milliseconds"),
            'realm': realm,
            'service': service,
            'process_id': ident,
        }

        result = self._execute(
            service,
            "process_execute",
            run_config=dict(
                ident=ident,
                request=request.model_dump(mode='json'),
                project_path=project,
            ),
            meta=meta,
            expiration_timeout=self._expiration_timeout,
            context=context,
        )

        job_id = result.id

        status = await asyncio.to_thread(
            self._job_status,
            job_id,
            self.destinations(service),
        )
        if not status:
            # Return default PENDING state
            status = JobStatus(
                job_id=job_id,
                status=JobStatus.PENDING,
                process_id=ident,
                created=created,
            )

        # Register pending task info
        registry.register(self._celery, service, realm, status, self._result_expires)

        return status

    # ==============================================
    #
    #    Note About pending messages:
    #
    #    When a job is created, it is put on rabbitmq
    #    queue waiting for beeing processeed.
    #
    #    A job may stay in pending state when no workers
    #    is alive to reserve the message. In this case,
    #    the message will not live more than the message
    #    expiration timeout (from the configuration).
    #
    #    Except from flushing the qeueues, it's not straightforward
    #    to track or revoke a pending message.
    #
    #    On job creation, a record is set
    #    into the job 'registry': amongst other things,
    #    this allow for checking the existence of
    #    'pending' messages.
    #
    #    That means that from the executor POV we cannot dismiss a
    #    pending message.
    #
    # ==============================================

    def _dismiss(self, job_id: str, services: ServiceDict) -> bool:
        # Dismiss job (blocking)
        # Check if job_id is registered
        ti = registry.find_job(self._celery, job_id)
        if ti and not ti.dismissed:
            destinations = self.get_destinations(ti.service, services)
            # Revoke task
            registry.dismiss(self._celery, job_id)
            logger.info("Revoking (DISMISS) job %s", job_id)
            self._celery.control.revoke(
                job_id,
                destination=destinations,
                terminate=True,
                signal='SIGKILL',
            )
        return ti is not None

    async def dismiss(self, job_id: str) -> bool:
        """ Dismiss job
        """
        return await asyncio.to_thread(self._dismiss, job_id, self._services)

    async def job_status(
        self,
        job_id: str,
        service: Optional[str] = None,
    ) -> Optional[JobStatus]:
        """ Return job status
        """
        return await asyncio.to_thread(
            self._job_status_ext,
            job_id,
            service and self.destinations(service),
        )

    def _job_status_ext(
        self,
        job_id: str,
        destinations: Optional[Sequence[str]] = None,
    ) -> Optional[JobStatus]:
        # Return job status (blocking) with pending state check
        st = self._job_status(job_id, destinations)
        if not st:
            # Give a chance to pending state
            ti = registry.find_job(self._celery, job_id)
            # Check if pending message has not expired
            if ti and time() < ti.created + self._expiration_timeout:
                st = JobStatus(
                    job_id=job_id,
                    status=JobStatus.PENDING,
                    process_id=ti.process_id,
                    created=to_utc_datetime(ti.created),
                )
        return st

    def _job_status(
        self,
        job_id: str,
        destinations: Optional[Sequence[str]] = None,
    ) -> Optional[JobStatus]:
        # Return job status (blocking)
        #
        # Get the state from the backend
        state = self._celery.backend.get_task_meta(job_id)

        logger.trace("=Job status %s", state)

        finished = None
        progress = None
        message = None
        updated = None

        match state['status']:
            case Celery.STATE_PENDING:
                # Retrieve scheduled jobs
                status, request = self._query_task(job_id, destinations)
                if not request:
                    return None  # No job
                match status:
                    case "active":
                        status = JobStatus.RUNNING
                    case "scheduled" | "reserved":
                        status = JobStatus.ACCEPTED
                    case "revoked":
                        status = JobStatus.DISMISSED
                    case _:
                        status = JobStatus.PENDING
                state['kwargs'] = request['kwargs']
            case Celery.STATE_STARTED:
                status = JobStatus.RUNNING
            case Celery.STATE_FAILURE:
                status = JobStatus.FAILED
                # Result contains the python exception raised
                message = str(state['result'])
                finished = state['date_done']
                progress = 100
            case Celery.STATE_SUCCESS:
                status = JobStatus.SUCCESS
                finished = state['date_done']
                progress = 100
            case Celery.STATE_REVOKED:
                status = JobStatus.DISMISSED
            case Celery.STATE_UPDATED:
                result = state['result']
                progress = result.get('progress')
                message = result.get('message')
                updated = result.get('updated')
                status = JobStatus.RUNNING
            case _ as unknown_state:
                # Unhandled state
                raise RuntimeError(f"Unhandled celery task state: {unknown_state}")

        meta = state['kwargs'].get('__meta__', {})

        return JobStatus(
            job_id=job_id,
            status=status,
            finished=finished,
            process_id=meta['process_id'],
            created=meta['created'],
            started=meta.get('started'),
            updated=updated,
            progress=progress,
            message=message,
        )

    def _query_task(
        self,
        job_id: str,
        destinations: Optional[Sequence[str]] = None,
    ) -> Tuple[Optional[str], Optional[Dict]]:
        #
        # schema is: { <destination>: { <job_id>: [state, <info>]}}}
        # state may be 'reserved', 'active', 'scheduled', 'revoked'
        #
        # See https://docs.celeryq.dev/en/stable/reference/celery.app.control.html#celery.app.control.Inspect.query_task

        result = self._celery.control.inspect(destinations).query_task(job_id)
        result = result and next(iter(result.values()))
        result = result and result.get(job_id)
        match result:
            case [status, infos]:
                result = (status, infos)
            case _ if not result:
                result = (None, None)
            case _ if result:
                raise ValueError(f"Invalid format for query task infos: {result}")
        return result

    async def job_results(
        self,
        job_id: str,
    ) -> Optional[JobResults]:
        """ Return job results
        """
        return await asyncio.to_thread(self._job_results, job_id)

    def _job_results(self, job_id):
        #
        # Return job results (blocking)
        #
        state = self._celery.backend.get_task_meta(job_id)
        if state['status'] == Celery.STATE_SUCCESS:
            return state['result']
        else:
            return None
