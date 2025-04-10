import itertools

from enum import IntEnum
from time import time
from typing import (
    Callable,
    Iterator,
    Optional,
    Sequence,
    TypedDict,
    assert_never,
)

from celery.result import AsyncResult
from pydantic import JsonValue

from qjazz_contrib.core import logger
from qjazz_contrib.core.celery import Celery
from qjazz_contrib.core.utils import to_utc_datetime, utc_now

from ..schemas import (
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
from ..worker import registry
from ..worker.exceptions import (
    DismissedTaskError,
    ProcessesException,
    ServiceNotAvailable,
)
from ..worker.models import Link, ProcessFiles, ProcessLog
from .protocols import ExecutorProtocol, ServiceDict

#
#  Processes
#

class JobMeta(TypedDict):
    created: str
    realm: Optional[str]
    service: str
    process_id: str
    expires: int
    tag: Optional[str]


class Processes(ExecutorProtocol):

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
        meta: JobMeta,
        context: Optional[JsonDict] = None,
        priority: int = 0,
        countdown: Optional[int] = None,
    ) -> AsyncResult:
        # Execute process (blocking)

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
            countdown=countdown,
        )

    # Helper for creating job meta and job registration
    class JobBuilder:
        def __init__(
            self,
            this: 'Processes',
            service: str,
            ident: str,
            *,
            pending_timeout: Optional[int],
            realm: Optional[str],
            tag: Optional[str],
            countdown: Optional[int],
        ):
            _, service_details = this._services[service]

            # Get the expiration time
            expires = service_details.result_expires

            # In synchronous mode, set the pending timeout
            # to the passed value or fallback to default
            pending_timeout = pending_timeout or this._pending_expiration_timeout

            # Takes countdown into account in expiration
            if countdown is not None:
                pending_timeout += countdown

            created = utc_now()

            meta: JobMeta = {
                "created": created.isoformat(timespec="milliseconds"),
                "realm": realm,
                "service": service,
                "process_id": ident,
                "expires": expires,
                "tag": tag,
            }

            self.created = created
            self.meta = meta
            self.expires = expires
            self.pending_timeout = pending_timeout

        def register(self, this: 'Processes', job_id: str) -> JobStatus:
            """Register job"""

            # create PENDING default state
            status = JobStatus(
                job_id=job_id,
                status=JobStatus.PENDING,
                process_id=self.meta['process_id'],
                created=self.created,
                tag=self.meta['tag'],
            )

            # Register pending task info
            registry.register(
                this._celery,
                self.meta['service'],
                self.meta['realm'],
                status,
                self.expires,
                self.pending_timeout,
            )

            return status

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
        priority: int = 0,
        countdown: Optional[int] = None,
    ) -> tuple[
        str,
        Callable[[int | None], JobResults],
        Callable[[], JobStatus],
    ]:
        """Send an execute request

        Returns a synchronous or asynchronous  'Result' object
        depending on the `sync` parameter.
        """

        builder = Processes.JobBuilder(
            self,
            service,
            ident,
            pending_timeout=pending_timeout,
            realm=realm,
            tag=tag,
            countdown=countdown,
        )

        result = self._execute_task(
            service,
            "process_execute",
            run_config=dict(
                ident=ident,
                request=request.model_dump(mode="json"),
                project_path=project,
            ),
            meta=builder.meta,
            pending_timeout=builder.pending_timeout,
            context=context,
            countdown=countdown,
        )

        job_id = result.id

        status = builder.register(self, job_id)

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

        if not ti.dismissed and now_ts < ti.created + ti.pending_timeout:
            st = JobStatus(
                job_id=ti.job_id,
                status=JobStatus.PENDING,
                process_id=ti.process_id,
                created=to_utc_datetime(ti.created),
                message="Task pending",
                tag=ti.tag,
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

        logger.trace("=Job status %s:  %s", job_id, state)

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
                        message = f"Task {status}"
                    case "scheduled" | "reserved":
                        status = JobStatus.ACCEPTED
                        message = f"Task {status}"
                    case "revoked":
                        status = JobStatus.DISMISSED
                        message = f"Task {status}"
                    case _:
                        status = JobStatus.PENDING
                        message = "Task pending"
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

        details: dict = {'tag': meta.get('tag')}
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

                logger.trace("=pull: %s", ti)

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
