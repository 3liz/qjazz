from aiohttp import web
from typing_extensions import List, Optional

from ..executor import Executor
from ._handlers import (
    Jobs,
    Processes,
    Services,
)
from .accesspolicy import AccessPolicy
from .utils import redirect


class Handler(Services, Processes, Jobs):

    def __init__(self,
        *,
        executor: Executor,
        policy: AccessPolicy,
        timeout: int,
        prefix: Optional[str] = None,
    ):
        self._executor = executor
        self._accesspolicy = policy
        self._timeout = timeout
        self._prefix = prefix or ""

    @property
    def routes(self) -> List[web.RouteDef]:
        prefix = self._prefix
        return [
            web.get(f"{prefix}/processes/", self.list_processes, allow_head=False),
            web.get(f"{prefix}/processes", redirect(f'{prefix}/processes/'), allow_head=False),
            web.get(f"{prefix}/processes/{{Ident}}", self.describe_process, allow_head=False),
            web.post(f"{prefix}/processes/{{Ident}}/execution", self.execute_process),
            web.get(f"{prefix}/jobs/", self.list_jobs, allow_head=False),
            web.get(f"{prefix}/jobs", redirect(f'{prefix}/jobs/'), allow_head=False),
            web.get(f"{prefix}/jobs/{{JobId}}", self.job_status, allow_head=False),
            web.delete(f"{prefix}/jobs/{{JobId}}", self.dismiss_job),
            web.get(f"{prefix}/jobs/{{JobId}}/results", self.job_results, allow_head=False),
        ]

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
    ) -> str:
        return self._accesspolicy.format_path(request, path, service)

    def get_service(self, request: web.Request) -> str:
        """ Get service name from request """
        service = self._accesspolicy.get_service(request)
        if not self._executor.known_service(service):
            raise web.HTTPNotFound(reason=f"Unknown service {service}")
        return service
