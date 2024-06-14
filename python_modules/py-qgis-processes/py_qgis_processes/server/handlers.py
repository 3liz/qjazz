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
    ):
        self._executor = executor
        self._accesspolicy = policy
        self._timeout = timeout

    @property
    def routes(self) -> List[web.RouteDef]:
        return [
            web.get("/processes/", self.list_processes, allow_head=False),
            web.get("/processes", redirect('/processes/'), allow_head=False),
            web.get("/processes/{Ident}", self.describe_process, allow_head=False),
            web.post("/processes/{Ident}/execution", self.execute_process),
            web.get("/jobs/", self.list_jobs, allow_head=False),
            web.get("/jobs", redirect('/jobs/'), allow_head=False),
            web.get("/jobs/{JobId}", self.job_status, allow_head=False),
            web.delete("/jobs/{JobId}", self.dismiss_job),
            web.get("/jobs/{JobId}/results", self.job_results, allow_head=False),
        ]

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
    ) -> str:
        prefix = request.get('prefix_path')
        if prefix:
            path = f"{prefix}{path}"
        return self._accesspolicy.format_path(request, path, service)

    def get_service(self, request: web.Request) -> str:
        """ Get service name from request """
        service = self._accesspolicy.get_service(request)
        if not self._executor.known_service(service):
            raise web.HTTPNotFound(reason=f"Unknown service {service}")
        return service
