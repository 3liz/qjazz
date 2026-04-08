from dataclasses import dataclass
from typing import (
    Callable,
    Optional,
    Sequence,
)

# Reexports
from .executor import (
    ExecutorBase,
    ExecutorConfig,  # noqa F401
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    Link,
    ProcessDescription,
    ProcessFiles,
    ProcessLog,
    ProcessSummary,
    ServiceDict,
)
from .processes import (
    Processes,
)

# =============================
# Executor; Synchronous version
# =============================


@dataclass
class Result:
    job_id: str
    get: Callable[[int | None], JobResults]
    status: Callable[[], JobStatus]


class BlockingExecutor(ExecutorBase):
    def update_services(self) -> ServiceDict:
        """Update services destinations"""
        return self._update_services(self.get_services())

    def describe(
        self,
        service: str,
        ident: str,
        *,
        project: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Optional[ProcessDescription]:
        """Return process description"""
        return self._describe(
            self.ensure_destinations(service),
            ident,
            project=project,
            timeout=timeout,
        )

    def processes(self, service: str, timeout: Optional[float] = None) -> Sequence[ProcessSummary]:
        """Return process description summary"""
        return self._processes(self.ensure_destinations(service), timeout)

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
        countdown: Optional[int] = None,
        priority: int = 0,
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
            countdown=countdown,
            priority=priority,
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

    job_results = Processes._job_results

    def jobs(
        self,
        service: Optional[str] = None,
        *,
        realm: Optional[str] = None,
        cursor: int = 0,
        limit: int = 100,
        with_details: bool = False,
    ) -> Sequence[JobStatus]:
        """Iterate over job statuses"""
        return self._jobs(
            self._services,
            service=service,
            realm=realm,
            cursor=cursor,
            limit=limit,
            with_details=with_details,
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
