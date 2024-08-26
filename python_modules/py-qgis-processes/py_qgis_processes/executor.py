
import asyncio
import itertools

from dataclasses import dataclass
from functools import partial
from textwrap import dedent as _D
from time import time

from celery.result import AsyncResult
from pydantic import Field, JsonValue
from typing_extensions import (
    Awaitable,
    Callable,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import Config as BaseConfig
from py_qgis_contrib.core.utils import to_utc_datetime, utc_now

from . import registry
from .celery import Celery, CeleryConfig
from .processing.schemas import (
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    JsonModel,
    LinkHttp,
    ProcessDescription,
    ProcessSummary,
    ProcessSummaryList,
    RunProcessingException,
)


class ExecutorConfig(BaseConfig):
    celery: CeleryConfig = CeleryConfig()

    message_expiration_timeout: int = Field(
        default=600,
        title="Message expiration timeout",
        description=_D(
            """
            The amount of time an execution message
            can wait on queue before beeing processed
            with asynchronous response.
            """,
        ),
    )


class PresenceDetails(JsonModel):
    service: str
    title: str
    description: str
    links: Sequence[LinkHttp]
    online_since: float
    qgis_version_info: int
    versions: str


ServiceDict = Dict[str, Tuple[Sequence[str], PresenceDetails]]


@dataclass
class Result:
    job_id: str
    get: Callable[[int], Awaitable[JobResults]]
    status: Callable[[], Awaitable[JobStatus]]


class Executor:

    def __init__(self, conf: Optional[ExecutorConfig] = None, *, name: Optional[str] = None):
        conf = conf or ExecutorConfig()
        self._celery = Celery(name, conf.celery)
        self._services: ServiceDict = {}
        self._pending_expiration_timeout = conf.message_expiration_timeout
        self._result_expires = conf.celery.result_expires
        self._last_updated = 0.

    def presences(self, destinations: Optional[Sequence[str]] = None) -> Dict[str, PresenceDetails]:
        """ Return presence info for online workers
        """
        data = self._celery.control.broadcast(
            'presence',
            reply=True,
            destination=destinations,
        )

        return {k: PresenceDetails.model_validate(v) for row in data for k, v in row.items()}

    def known_service(self, name: str) -> bool:
        """ Check if service is known in uploaded presences
        """
        return name in self._services

    @property
    def services(self) -> Iterator[PresenceDetails]:
        """ Return uploaded services presences
        """
        for _, pr in self._services.values():
            yield pr

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
        self._last_updated = time()
        return self._services

    @property
    def last_updated(self):
        return self._last_updated

    @classmethod
    def get_destinations(cls, service: str, services: ServiceDict) -> Optional[Sequence[str]]:
        item = services.get(service)
        return item and item[0]

    def destinations(self, service: str) -> Optional[Sequence[str]]:
        return self.get_destinations(service, self._services)

    def _describe(
        self,
        service: str,
        ident: str,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
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
        timeout: Optional[int] = None,
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

    async def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """ Return process description summary
        """
        return await asyncio.to_thread(
            self._processes,
            service,
            timeout,
        )

    def _execute_task(
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
        pending_timeout: Optional[int] = None,
    ) -> Result:
        """ Send an execute request

            Returns a 'Result' object
        """
        created = utc_now()
        meta = {
            'created': created.isoformat(timespec="milliseconds"),
            'realm': realm,
            'service': service,
            'process_id': ident,
        }

        # In synchronous mode, set the pending timeout
        # the the passed value of fallback to default
        pending_timeout = pending_timeout or self._pending_expiration_timeout

        result = self._execute_task(
            service,
            "process_execute",
            run_config=dict(
                ident=ident,
                request=request.model_dump(mode='json'),
                project_path=project,
            ),
            meta=meta,
            expiration_timeout=pending_timeout,
            context=context,
        )

        job_id = result.id

        # create PENDING default state
        status = JobStatus(
            job_id=job_id,
            status=JobStatus.PENDING,
            process_id=ident,
            created=created,
        )

        # Register pending task info
        registry.register(
            self._celery,
            service,
            realm,
            status,
            self._result_expires,
            pending_timeout,
        )

        def _get_status() -> JobStatus:
            return self._job_status(job_id, self.destinations(service)) or status

        def _get_result(timeout: Optional[int] = None) -> JobResults:
            return result.get(timeout=timeout)

        return Result(
            job_id=job_id,
            get=partial(asyncio.to_thread, _get_result),
            status=partial(asyncio.to_thread, _get_status),
        )

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

    def _job_status_pending(self, ti: registry.TaskInfo) -> Optional[JobStatus]:
        # Give a chance to pending state
        # Check if pending message has not expired
        st: JobStatus | None
        if time() < ti.created + ti.pending_timeout:
            st = JobStatus(
                job_id=ti.job_id,
                status=JobStatus.PENDING,
                process_id=ti.process_id,
                created=to_utc_datetime(ti.created),
            )
        else:
            st = None
        return st

    def _dismiss(
        self,
        job_id: str,
        services: ServiceDict,
        realm: Optional[str] = None,
    ) -> Optional[JobStatus]:
        # Dismiss job (blocking)
        # Check if job_id is registered
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        if not ti.dismissed:
            # Revoke task
            registry.dismiss(self._celery, job_id)
            logger.info("Revoking (DISMISS) job %s", job_id)
            self._celery.control.revoke(
                job_id,
                destination=destinations,
                terminate=True,
                signal='SIGKILL',
            )

        st = self._job_status(job_id, destinations)
        return st or self._job_status_pending(ti)

    async def dismiss(self, job_id: str, *, realm: Optional[str] = None) -> Optional[JobStatus]:
        """ Dismiss job
        """
        return await asyncio.to_thread(
            self._dismiss,
            job_id,
            self._services,
            realm=realm,
        )

    async def job_status(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        with_details: bool = False,
    ) -> Optional[JobStatus]:
        """ Return job status
        """
        return await asyncio.to_thread(
            self._job_status_ext,
            job_id,
            self._services,
            realm,
            with_details,
        )

    def _job_status_ext(
        self,
        job_id: str,
        services: ServiceDict,
        realm: Optional[str] = None,
        with_details: bool = False,
    ) -> Optional[JobStatus]:
        # Return job status (blocking) with pending state check
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        st = self._job_status(job_id, destinations, with_details)
        return st or self._job_status_pending(ti)

    def _job_status(
        self,
        job_id: str,
        destinations: Optional[Sequence[str]] = None,
        with_details: bool = False,
    ) -> Optional[JobStatus]:
        # Return job status (blocking)
        #
        # Get the state from the backend
        state = self._celery.backend.get_task_meta(job_id)

        logger.trace("=Job status %s", state)

        finished = None
        progress = None
        updated = None
        message = ""

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
                message = "Task started"
            case Celery.STATE_FAILURE:
                status = JobStatus.FAILED
                # Result contains the python exception raised
                match state['result']:
                    case InputValueError() as err:
                        message = str(err)
                    case RunProcessingException() as err:
                        message = "Internal processing error"
                    case Exception():
                        message = "Internal worker error"
                    case msg:
                        message = msg
                finished = state['date_done']
                progress = 100
            case Celery.STATE_SUCCESS:
                status = JobStatus.SUCCESS
                finished = state['date_done']
                message = "Task finished"
                progress = 100
            case Celery.STATE_REVOKED:
                finished = state['date_done']
                message = "Task dismissed"
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

        # Get task arguments
        kwargs = state['kwargs']
        meta = kwargs.get('__meta__', {})

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
            run_config=kwargs.get('__run_config__') if with_details else None,
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
        *,
        realm: Optional[str] = None,
    ) -> Optional[JobResults]:
        """ Return job results
        """
        return await asyncio.to_thread(self._job_results, job_id, realm)

    def _job_results(self, job_id: str, realm: Optional[str] = None) -> Optional[JobResults]:
        #
        # Return job results (blocking)
        #
        if realm and not registry.find_key(self._celery, job_id, realm=realm):
            return None

        state = self._celery.backend.get_task_meta(job_id)
        if state['status'] == Celery.STATE_SUCCESS:
            return state['result']
        else:
            return None

    async def jobs(
        self,
        service: Optional[str] = None,
        *,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> Sequence[JobStatus]:
        """ Iterate over job statuses
        """
        destinations = service and self.destinations(service)

        def _pull() -> Sequence[JobStatus]:
            keys = registry.find_keys(self._celery, service, realm=realm)
            data = []
            for job_id, _, _ in itertools.islice(keys, cursor, cursor + limit):
                st = self._job_status(job_id, destinations)
                if not st:
                    ti = registry.find_job(self._celery, job_id)
                    st = self._job_status_pending(ti) if ti else None
                if st:
                    data.append(st)

            return data

        return await asyncio.to_thread(_pull)
