from importlib import resources
from pathlib import Path

from aiohttp import web
from typing_extensions import List, Optional

from ..executor import Executor
from ._handlers import (
    Jobs,
    Processes,
    Services,
    WebUI,
)
from .accesspolicy import AccessPolicy
from .cache import ProcessesCache
from .models import ErrorResponse
from .utils import redirect_trailing_slash

API_VERSION = "v1"
PAGKAGE_NAME = "py_qgis_processes"


class Handler(Services, Processes, Jobs, WebUI):

    def __init__(self,
        *,
        executor: Executor,
        policy: AccessPolicy,
        cache: ProcessesCache,
        timeout: int,
    ):
        self._executor = executor
        self._accesspolicy = policy
        self._timeout = timeout
        self._cache = cache

        self._staticpath = Path(str(resources.files(PAGKAGE_NAME))).joinpath("server", "html")

    @property
    def routes(self) -> List[web.RouteDef]:
        prefix = self._accesspolicy.prefix
        return [
            # Services
            web.get(f"{prefix}/processes/", self.list_processes, allow_head=False),
            web.get(f"{prefix}/processes", redirect_trailing_slash(), allow_head=False),
            web.get(f"{prefix}/processes/{{Ident}}", self.describe_process, allow_head=False),
            web.post(f"{prefix}/processes/{{Ident}}/execution", self.execute_process),

            # Jobs
            web.get(f"{prefix}/jobs/", self.list_jobs, allow_head=False),
            web.get(f"{prefix}/jobs", redirect_trailing_slash(), allow_head=False),

            web.get(f"{prefix}/jobs.html", redirect_trailing_slash(), allow_head=False),
            web.get(f"{prefix}/jobs.html/{{Path:.*}}", self.ui_dashboard, allow_head=False),
            web.get(
                rf"{prefix}/jobs/{{JobId:[^/\.]+\.html}}",
                redirect_trailing_slash(),
                allow_head=False,
            ),
            web.get(
                rf"{prefix}/jobs/{{JobId:[^/\.]+\.html}}/{{Path:.*}}",
                self.ui_jobdetails,
                allow_head=False,
            ),

            web.get(f"{prefix}/jobs/{{JobId}}", self.job_status, allow_head=False),
            web.delete(f"{prefix}/jobs/{{JobId}}", self.dismiss_job),
            web.get(f"{prefix}/jobs/{{JobId}}/results", self.job_results, allow_head=False),

            web.get(f"{prefix}/services/", self.list_services, allow_head=False),
            web.get(f"{prefix}/services", redirect_trailing_slash(), allow_head=False),
        ]

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
        project: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> str:
        return self._accesspolicy.format_path(
            request,
            path,
            service,
            project,
            query=query,
        )

    def get_service(self, request: web.Request, raise_error: bool = True) -> str:
        """ Get known service name from request """
        service = self._accesspolicy.get_service(request)
        if raise_error and not self._executor.known_service(service):
            ErrorResponse.raises(web.HTTPServiceUnavailable, "Service not known")
        return service

    def get_project(self, request: web.Request) -> Optional[str]:
        project = self._accesspolicy.get_project(request)
        # Ensure that project starts with '/'
        if project and not project.startswith('/'):
            project = f"/{project}"
        return project
        if project and not project.startswith('/'):
            project = f"/{project}"

        if project and not project.startswith('/'):
            project = f"/{project}"
