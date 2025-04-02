import itertools

from dataclasses import dataclass
from enum import IntEnum
from random import randint
from time import time
from typing import (
    Callable,
    Iterator,
    Mapping,
    Optional,
    Sequence,
    assert_never,
    cast,
)

from celery.result import AsyncResult
from pydantic import Field, JsonValue

from qjazz_contrib.core import logger
from qjazz_contrib.core.celery import Celery, CeleryConfig
from qjazz_contrib.core.config import ConfigBase
from qjazz_contrib.core.utils import to_utc_datetime, utc_now

from .schemas import (
    DateTime,
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    ProcessDescription,
    ProcessSummary,
    ProcessSummaryList,
    RunProcessException,
)
from .worker import registry
from .worker.exceptions import (
    DismissedTaskError,
    ProcessesException,
    ServiceNotAvailable,
    UnreachableDestination,
)
from .worker.models import Link, ProcessFiles, ProcessLog, WorkerPresence


class ExecutorConfig(ConfigBase):
    celery: CeleryConfig = CeleryConfig()

    message_expiration_timeout: int = Field(
        default=600,
        title="Message expiration timeout",
        description="""
        The amount of time an execution message
        can wait on queue before beeing processed
        with asynchronous response.
        """,
    )


PresenceDetails = WorkerPresence

ServiceDict = dict[str, tuple[Sequence[str], PresenceDetails]]


#
# Process executor
#


class _ExecutorBase:
    def __init__(self, conf: Optional[ExecutorConfig] = None, *, name: Optional[str] = None):
        conf = conf or ExecutorConfig()

        self._celery = Celery(name, conf.celery)
        self._services: ServiceDict = {}
        self._last_updated = 0.0

        self._pending_expiration_timeout = conf.message_expiration_timeout
        self._default_result_expires = conf.celery.result_expires

    def presences(self, destinations: Optional[Sequence[str]] = None) -> dict[str, PresenceDetails]:
        """Return presence info for online workers"""
        data = self._celery.control.broadcast(
            "presence",
            reply=True,
            destination=destinations,
        )

        return {k: PresenceDetails.model_validate(v) for row in data for k, v in row.items()}

    def known_service(self, name: str) -> bool:
        """Check if service is known in uploaded presences"""
        return name in self._services

    @property
    def services(self) -> Iterator[PresenceDetails]:
        """Return uploaded services presences"""
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

    def command(
        self,
        name: str,
        *,
        destination: Sequence[str],
        broadcast: bool = False,
        reply: bool = True,
        **kwargs,
    ) -> JsonValue:
        """Send an inspect command to one or more service instances"""
        if not broadcast:
            # Pick a destination randomly, so that we can
            # use all availables workers
            index = randint(0, len(destination) - 1)  # nosec B311
            destination = (destination[index],)

        resp = self._celery.control.broadcast(
            name,
            destination=destination,
            reply=reply,
            **kwargs,
        )

        logger.trace("=command '%s': %s", name, resp)

        if reply and not resp:
            raise UnreachableDestination(f"{destination}")

        if not reply:
            return None

        if not broadcast:
            return next(iter(resp[0].values()))
        else:
            return dict(next(iter(r.items())) for r in resp)

    #
    # Control commands
    #

    def _dests(self, service: str) -> Sequence[str]:
        dests = self.destinations(service)
        if not dests:
            raise ServiceNotAvailable(service)
        return dests

    def restart_pool(self, service: str, *, timeout: float = 5.0) -> JsonValue:
        """Restart worker pool"""
        return self._celery.control.pool_restart(
            destination=self._dests(service),
            reply=True,
            timeout=timeout,
        )

    def ping(self, service: str, timeout: float = 1.0) -> JsonValue:
        """Ping service workers"""
        return self._celery.control.ping(self._dests(service), timeout=timeout)

    def shutdown(self, service: str, *, reply: bool = True, timeout: float = 5.0) -> JsonValue:
        return self._celery.control.shutdown(
            self._dests(service),
            reply=reply,
            timeout=timeout,
        )

    #
    # Processes
    #

    def _describe(
        self,
        destinations: Sequence[str],
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[ProcessDescription]:
        # Retrieve process description (blocking version)
        res = self.command(
            "describe_process",
            destination=destinations,
            arguments={"ident": ident, "project_path": project},
            timeout=timeout,
        )

        return ProcessDescription.model_validate(res) if res else None

    def _processes(
        self,
        destinations: Sequence[str],
        timeout: Optional[float] = None,
    ) -> Sequence[ProcessSummary]:
        # List processes for service (blocking version)
        res = self.command(
            "list_processes",
            destination=destinations,
            timeout=timeout,
        )

        return ProcessSummaryList.validate_python(res)

    def _execute_task(
        self,
        service: str,
        task: str,
        run_config: dict[str, JsonValue],
        *,
        pending_timeout: int,
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
            queue=f"qjazz.{service}",
            expires=pending_timeout,
            kwargs={
                "__meta__": meta,
                "__context__": context,
                "__run_config__": run_config,
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
        tag: Optional[str] = None,
    ) -> tuple[
        str,
        Callable[[int | None], JobResults],
        Callable[[], JobStatus],
    ]:
        """Send an execute request

        Returns a synchronous or asynchronous  'Result' object
        depending on the `sync` parameter.
        """
        _, service_details = self._services[service]

        # Get the expiration time
        expires = service_details.result_expires

        # In synchronous mode, set the pending timeout
        # to the passed value or fallback to default
        pending_timeout = pending_timeout or self._pending_expiration_timeout

        if pending_timeout > expires:
            # XXX Pending timeout must be lower than expiration timeout
            pending_timeout = expires

        created = utc_now()

        meta = {
            "created": created.isoformat(timespec="milliseconds"),
            "realm": realm,
            "service": service,
            "process_id": ident,
            "expires": expires,
            "tag": tag,
        }

        result = self._execute_task(
            service,
            "process_execute",
            run_config=dict(
                ident=ident,
                request=request.model_dump(mode="json"),
                project_path=project,
            ),
            meta=meta,
            pending_timeout=pending_timeout,
            context=context,
        )

        job_id = result.id

        # create PENDING default state
        status = JobStatus(
            job_id=job_id,
            status=JobStatus.PENDING,
            process_id=ident,
            created=created,
            tag=meta['tag'],
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
    #    Except from flushing the queues, it's not straightforward
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

        # Lock accross multiple server instances
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
        match state["status"]:
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
                    match st:
                        case "active" | "scheduled" | "reserved":
                            # Task has been received by the worker
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
                        signal="SIGKILL",
                        reply=True,
                        timeout=timeout,
                    )
                    logger.trace("=Revoke returned: %s", rv)
                    # Check the state status:
                    state = self._celery.backend.get_task_meta(job_id)
                    logger.trace("=State returned: %s", state)
                    if state["status"] != Celery.STATE_REVOKED:
                        logger.warning(
                            "%s: task was revoked but still in' %s' state",
                            job_id,
                            state["status"],
                        )
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

        match state["status"]:
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
                state["kwargs"] = request["kwargs"]
            case Celery.STATE_STARTED:
                status = JobStatus.RUNNING
                message = "Task started"
            case Celery.STATE_FAILURE:
                status = JobStatus.FAILED
                # Result contains the python exception raised
                match state["result"]:
                    case InputValueError() as err:
                        message = str(err)
                    case DismissedTaskError():
                        # Attempt to run a dismissed task
                        message = "Dismissed task"
                        status = JobStatus.DISMISSED
                    case RunProcessException():
                        message = "Internal processing error"
                    case ProcessesException() as err:
                        message = str(err)
                    case Exception():
                        message = "Internal worker error"
                    case msg:
                        message = msg
                finished = state["date_done"]
                progress = 100
            case Celery.STATE_SUCCESS:
                status = JobStatus.SUCCESS
                finished = state["date_done"]
                message = "Task finished"
                progress = 100
            case Celery.STATE_REVOKED:
                finished = state["date_done"]
                message = "Task dismissed"
                status = JobStatus.DISMISSED
            case Celery.STATE_UPDATED:
                result = state["result"]
                progress = result.get("progress")
                message = result.get("message")
                updated = result.get("updated")
                status = JobStatus.RUNNING
            case _ as unknown_state:
                # Unhandled state
                raise RuntimeError(f"Unhandled celery task state: {unknown_state}")

        # Get task arguments
        kwargs = state["kwargs"]
        meta = kwargs.get("__meta__", {})

        details: dict = { 'tag': meta.get('tag') }
        if with_details:
            details.update(run_config=kwargs.get("request"))
            if finished:
                end_at = DateTime.validate_python(finished).timestamp()
                details.update(
                    expires_at=to_utc_datetime(meta["expires"] + end_at),
                )

        return JobStatus(
            job_id=job_id,
            status=status,
            finished=finished,
            process_id=meta["process_id"],
            created=meta["created"],
            started=meta.get("started"),
            updated=updated,
            progress=progress,
            message=message,
            **details,
        )

    def _query_task(
        self,
        job_id: str,
        destinations: Optional[Sequence[str]] = None,
    ) -> tuple[Optional[str], Optional[dict]]:
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
        if state["status"] == Celery.STATE_SUCCESS:
            return state["result"]
        else:
            return None

    def _jobs(
        self,
        services: ServiceDict,
        *,
        service: Optional[str] = None,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
    ) -> Sequence[JobStatus]:
        """Iterate over job statuses"""

        def _pull() -> Iterator[JobStatus]:
            destinations = service and self.get_destinations(service, services)
            for job_id, _, _ in registry.find_keys(self._celery, service, realm=realm):
                # Get job task info
                # which is much faster than checking job status first
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

    def _log_details(
        self,
        job_id: str,
        services: ServiceDict,
        *,
        timeout: int,
        realm: Optional[str] = None,
    ) -> Optional[ProcessLog]:
        """Return process execution logs (blocking)"""
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(ti.service)

        response = self.command(
            "job_log",
            arguments={"job_id": job_id},
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
        """Return process execution files (blocking)"""
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(ti.service)

        response = self.command(
            "job_files",
            arguments={"job_id": job_id, "public_url": public_url},
            destination=destinations,
            timeout=timeout,
        )

        match response:
            case {"error": msg}:
                raise RuntimeError(f"Command 'process_files' failed with msg: {msg}")
            case _:
                return ProcessFiles.model_validate(response)

    def _download_url(
        self,
        job_id: str,
        services: ServiceDict,
        *,
        resource: str,
        timeout: int,
        expiration: int,
        realm: Optional[str] = None,
    ) -> Optional[Link]:
        """Return download_url (blocking)"""
        ti = registry.find_job(self._celery, job_id, realm=realm)
        if not ti:
            return None

        destinations = self.get_destinations(ti.service, services)
        # XXX Check that services are online (test for presence)
        if not destinations:
            raise ServiceNotAvailable(ti.service)

        response = self.command(
            "download_url",
            arguments={"job_id": job_id, "resource": resource, "expiration": expiration},
            destination=destinations,
            timeout=timeout,
        )

        match response:
            case {"error": msg}:
                raise RuntimeError(f"Command 'process_files' failed with msg: {msg}")
            case None:
                return None
            case _:
                return Link.model_validate(response)


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
        """Update services destinations

        Collapse presence details under unique service
        name.
        """
        self._services = self.get_services()
        logger.trace("=update_services %s", self._services)
        self._last_updated = time()
        return self._services

    def describe(
        self,
        service: str,
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[ProcessDescription]:
        """Return process description"""
        destinations = self.destinations(service)
        if not destinations:
            raise ServiceNotAvailable(service)

        return self._describe(
            destinations,
            ident,
            project=project,
            timeout=timeout,
        )

    def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """Return process description summary"""
        destinations = self.destinations(service)
        if not destinations:
            raise ServiceNotAvailable(service)

        return self._processes(destinations, timeout)

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
        tag: Optional[str] = None,
    ) -> Result:
        job_id, _get_result, _get_status = self._execute(
            service,
            ident,
            request,
            project=project,
            context=context,
            realm=realm,
            pending_timeout=pending_timeout,
            tag=tag,
        )
        return Result(job_id=job_id, get=_get_result, status=_get_status)

    def dismiss(
        self,
        job_id: str,
        *,
        realm: Optional[str] = None,
        timeout: int = 20,
    ) -> Optional[JobStatus]:
        """Delete job"""
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
        """Return job status"""
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
        """Iterate over job statuses"""
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
        """Return process execution logs"""
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
        """Return process execution files"""
        return self._files(
            job_id,
            self._services,
            public_url=public_url,
            realm=realm,
            timeout=timeout,
        )

    def download_url(
        self,
        job_id: str,
        *,
        resource: str,
        timeout: int,
        expiration: int,
        realm: Optional[str] = None,
    ) -> Optional[Link]:
        """Return download url"""
        return self._download_url(
            job_id,
            self._services,
            resource=resource,
            expiration=expiration,
            timeout=timeout,
            realm=realm,
        )
