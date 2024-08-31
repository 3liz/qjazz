
import itertools

from dataclasses import dataclass
from enum import IntEnum
from textwrap import dedent as _D
from time import time

from celery.result import AsyncResult
from pydantic import Field, JsonValue
from typing_extensions import (
    Callable,
    Dict,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    assert_never,
    cast,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_postcondition
from py_qgis_contrib.core.config import Config as BaseConfig
from py_qgis_contrib.core.utils import to_utc_datetime, utc_now

from . import registry
from .celery import Celery, CeleryConfig
from .exceptions import (
    DismissedTaskError,
    ServiceNotAvailable,
    UnreachableDestination,
)
from .models import ProcessFiles, ProcessLog, WorkerPresence
from .processing.schemas import (
    DateTime,
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
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


PresenceDetails = WorkerPresence

ServiceDict = Dict[str, Tuple[Sequence[str], PresenceDetails]]


class _ExecutorBase:

    def __init__(self, conf: Optional[ExecutorConfig] = None, *, name: Optional[str] = None):
        conf = conf or ExecutorConfig()
        self._celery = Celery(name, conf.celery)
        self._services: ServiceDict = {}
        self._pending_expiration_timeout = conf.message_expiration_timeout
        self._default_result_expires = conf.celery.result_expires
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

    @property
    def last_updated(self) -> float:
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
        *,
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

    def _execute(
        self,
        service: str,
        ident: str,
        request: JobExecute,
        *,
        project: Optional[str] = None,
        context: Optional[JsonDict] = None,
        realm: Optional[str] = None,
        pending_timeout: Optional[int] = None,
    ) -> Tuple[
        str,
        Callable[[int | None], JobResults],
        Callable[[], JobStatus],
    ]:
        """ Send an execute request

            Returns a synchronous or asynchronous  'Result' object
            depending on the `sync` parameter.
        """
        _, service_details = self._services[service]

        # Get the  expiration time
        expires = service_details.result_expires

        # In synchronous mode, set the pending timeout
        # the the passed value of fallback to default
        pending_timeout = pending_timeout or self._pending_expiration_timeout

        if pending_timeout > expires:
            # XXX Pending timeout must be lower than expiration timeout
            pending_timeout = expires

        created = utc_now()

        meta = {
            'created': created.isoformat(timespec="milliseconds"),
            'realm': realm,
            'service': service,
            'process_id': ident,
            'expires': expires,
        }

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
            expires,
            pending_timeout,
        )

        def _get_status() -> JobStatus:
            return self._job_status(job_id, self.destinations(service)) or status

        def _get_result(timeout: Optional[int] = None) -> JobResults:
            return result.get(timeout=timeout)

        return (job_id, _get_result, _get_status)

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
        now_ts = time()

        # NOTE: We expect the expiration timeout beeing larger than the pending
        # timeout
        if not ti.dismissed and now_ts < ti.created + ti.pending_timeout:

            st = JobStatus(
                job_id=ti.job_id,
                status=JobStatus.PENDING,
                process_id=ti.process_id,
                created=to_utc_datetime(ti.created),
            )
        else:
            # Job has expired/dismissed
            st = None
        return st

    def _dismiss(
        self,
        job_id: str,
        services: ServiceDict,
        realm: Optional[str],
        timeout: int = 20,
    ) -> Optional[JobStatus]:
        # Dismiss job (blocking)

        # Lock accross multiple server instance
        with registry.lock(self._celery, f"job:{job_id}", timeout=timeout):

            # Check if job_id is registered
            ti = registry.find_job(self._celery, job_id, realm=realm)
            if not ti:
                return None

            # Do not dismiss twice
            if ti.dismissed:
                raise DismissedTaskError(ti.job_id)

            service = ti.service

            # Get job status
            destinations = self.get_destinations(service, services)
            # XXX Check that services are online (test for presence)
            if not destinations:
                raise ServiceNotAvailable(service)

            logger.trace("=_dismiss:%s:%s", job_id, ti)

            # Mark item as dismissed
            registry.dismiss(self._celery, job_id)

        class _S(IntEnum):
            PENDING = 1
            ACTIVE = 2
            DONE = 3

        state = self._celery.backend.get_task_meta(job_id)
        match state['status']:
            case Celery.STATE_PENDING:
                # Retrieve scheduled jobs
                st, request = self._query_task(job_id, destinations)
                if not request:
                    now_ts = time()
                    if now_ts < ti.created + ti.pending_timeout:
                        status = _S.PENDING
                    else:
                        status = _S.DONE  # job has expired
                else:
                    match st, request:
                        case "active" | "scheduled" | "reserved":
                            status = _S.ACTIVE
                        case "revoked":
                            status = _S.DONE
                        case _:
                            logger.warning("Unhandled job status %s", st)
                            status = _S.PENDING
            case Celery.STATE_UPDATED | Celery.STATE_STARTED:
                status = _S.ACTIVE
            case Celery.STATE_FAILURE | Celery.STATE_SUCCESS | Celery.STATE_REVOKED:
                status = _S.DONE
            case _ as unknown_state:
                # Unhandled state
                raise RuntimeError(f"Unhandled celery task state: {unknown_state}")

        logger.info("%s: dismissing job with status %s", job_id, status)

        try:
            match status:
                case _S.ACTIVE:
                    # Job is revokable
                    rv = self._celery.control.revoke(
                        job_id,
                        destination=destinations,
                        terminate=True,
                        signal='SIGKILL',
                        reply=True,
                        timeout=timeout,
                    )
                    logger.trace("=Revoke returned: %s", rv)
                    # Check the state status:
                    state = self._celery.backend.get_task_meta(job_id)
                    assert_postcondition(state['status'] == Celery.STATE_REVOKED)
                case _S.DONE | _S.PENDING:
                    # Job is not revokable
                    pass
                case _ as unreachable:
                    assert_never(unreachable)

            # Delete registry entry
            # and let the worker do the cleanup
            registry.delete(self._celery, job_id)

            return JobStatus(
                job_id=ti.job_id,
                status=JobStatus.DISMISSED,
                process_id=ti.process_id,
                created=to_utc_datetime(ti.created),
            )
        except Exception:
            logger.error(f"Failed to dismiss job {job_id}")
            # Reset dismissed state
            registry.dismiss(self._celery, job_id, reset=True)
            raise

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
                logger.trace("=Job pending request (%s)  %s", status, request)
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
                    case DismissedTaskError():
                        # Attempt to run a dismissed task
                        message = "Dismissed task"
                        status = JobStatus.DISMISSED
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

        details: Dict = {}
        if with_details:
            details.update(run_config=kwargs.get('request'))
            if finished:
                end_at = DateTime.validate_python(finished).timestamp()
                details.update(
                    expires_at=to_utc_datetime(meta['expires'] + end_at),
                )

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
            **details,
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
        logger.trace("=query_task: %s", result)
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

    def _job_results(self, job_id: str, *, realm: Optional[str] = None) -> Optional[JobResults]:
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

    def scan_jobs(
        self,
        service: Optional[str] = None,
        realm: Optional[str] = None,
    ) -> Iterator[Tuple[str, str, str]]:
        """ Iterate over all registered jobs """
        return registry.find_keys(self._celery, service=service, realm=realm)

    def _jobs(
        self,
        services: ServiceDict,
        *,
        service: Optional[str] = None,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> Sequence[JobStatus]:
        """ Iterate over job statuses
        """
        def _pull() -> Iterator[JobStatus]:
            destinations = service and self.get_destinations(service, services)
            for job_id, _, _ in registry.find_keys(self._celery, service, realm=realm):
                # Get job task info
                # wich is much faster than checking job status first
                ti = registry.find_job(self._celery, job_id)
                if not ti:
                    continue

                if not service:
                    destinations = self.get_destinations(ti.service, services)

                st = self._job_status(ti.job_id, destinations)
                if not st:
                    st = self._job_status_pending(ti)
                if st:
                    yield st

        return list(itertools.islice(_pull(), cursor, cursor + limit))

    def command(
        self,
        name: str,
        *,
        broadcast: bool = False,
        reply: bool = True,
        destination: Sequence[str],
        **kwargs,
    ) -> JsonValue:
        """ Send an inspect command to one or more service instances """
        if not broadcast:
            destination = (destination[0],)

        resp = self._celery.control.broadcast(
            name,
            destination=destination,
            reply=reply,
            **kwargs,
        )

        logger.trace("=_command '%s': %s", name, resp)

        if reply and not resp:
            raise UnreachableDestination(f"{destination}")

        if not broadcast:
            return next(iter(resp[0].values()))
        else:
            return dict(next(iter(r.items())) for r in resp)

    def _log_details(
        self,
        job_id: str,
        services: ServiceDict,
        *,
        timeout: int,
        realm: Optional[str] = None,
    ) -> Optional[ProcessLog]:
        """ Return process execution logs (blocking) """
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(ti.service)

        response = self.command(
            'job_log',
            arguments={'job_id': job_id},
            destination=destinations,
            timeout=timeout,
        )

        match response:
            case {"error": msg}:
                raise RuntimeError(f"Command 'process_log' failed with msg: {msg}")
            case _:
                return ProcessLog.model_validate(response)

    def _files(
        self,
        job_id: str,
        services: ServiceDict,
        *,
        public_url: Optional[str],
        timeout: int,
        realm: Optional[str] = None,
    ) -> Optional[ProcessFiles]:
        """ Return process execution files (blocking) """
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(ti.service)

        response = self.command(
            'job_files',
            arguments={'job_id': job_id, 'public_url': public_url},
            destination=destinations,
            timeout=timeout,
        )

        match response:
            case {"error": msg}:
                raise RuntimeError(f"Command 'process_files' failed with msg: {msg}")
            case _:
                return ProcessFiles.model_validate(response)

    def restart_pool(self, service: str, *, reply: bool = True) -> JsonValue:
        """ Restart worker pool
        """
        destinations = self.destinations(service)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(service)

        return self.command('pool_restart', destination=destinations, reply=reply)


# =============================
# Executor; Synchronous version
# =============================

@dataclass
class Result:
    job_id: str
    get: Callable[[int | None], JobResults]
    status: Callable[[], JobStatus]


class Executor(_ExecutorBase):

    def update_services(self) -> ServiceDict:
        """ Update services destinations

            Collapse presence details under unique service
            name.
        """
        self._services = self.get_services()
        logger.trace("=update_services %s", self._services)
        self._last_updated = time()
        return self._services

    describe = _ExecutorBase._describe
    processes = _ExecutorBase._processes

    def execute(
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

        job_id, _get_result, _get_status = self._execute(
            service,
            ident,
            request,
            project=project,
            context=context,
            realm=realm,
            pending_timeout=pending_timeout,
        )
        return Result(job_id=job_id, get=_get_result, status=_get_status)

    def dismiss(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[JobStatus]:
        """ Delete job """
        return self._dismiss(
            job_id,
            self._services,
            realm=realm,
            timeout=timeout,
        )

    def job_status(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        with_details: bool = False,
    ) -> Optional[JobStatus]:
        """ Return job status """
        return self._job_status_ext(
            job_id,
            self._services,
            realm,
            with_details,
        )

    job_results = _ExecutorBase._job_results

    def jobs(
        self,
        service: Optional[str] = None,
        *,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> Sequence[JobStatus]:
        """ Iterate over job statuses """
        return self._jobs(
            self._services,
            service=service,
            realm=realm,
            cursor=cursor,
            limit=limit,
        )

    def log_details(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[ProcessLog]:
        """ Return process execution logs """
        return self._log_details(
            job_id,
            self._services,
            realm=realm,
            timeout=timeout,
        )

    def files(
        self,
        job_id: str,
        *,
        public_url: Optional[str] = None,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[ProcessFiles]:
        """ Return process execution files """
        return self._files(
            job_id,
            self._services,
            public_url=public_url,
            realm=realm,
            timeout=timeout,
        )
