from importlib import resources
from pathlib import Path
from typing import Optional

from aiohttp import web

from ._handlers import (
    Jobs,
    LandingPage,
    Processes,
    Services,
    Storage,
    WebUI,
)
from .accesspolicy import AccessPolicy
from .executor import AsyncExecutor
from .jobrealm import JobRealmConfig
from .models import ErrorResponse
from .storage import StorageConfig
from .utils import redirect_trailing_slash

API_VERSION = "v1"
PAGKAGE_NAME = "qjazz_processes"


class Handler(Services, Processes, Jobs, WebUI, Storage, LandingPage):
    def __init__(
        self,
        *,
        executor: AsyncExecutor,
        policy: AccessPolicy,
        timeout: int,
        enable_ui: bool,
        jobrealm: JobRealmConfig,
        storage: StorageConfig,
    ):
        self._executor = executor
        self._accesspolicy = policy
        self._timeout = timeout
        self._enable_ui = enable_ui
        self._jobrealm = jobrealm
        self._storage = storage

        self._staticpath = Path(str(resources.files(PAGKAGE_NAME))).joinpath("server", "html")

    @property
    def routes(self) -> list[web.RouteDef]:
        prefix = self._accesspolicy.prefix
        _routes = [
            # Landing page
            web.get(f"{prefix}/", self.landing_page, allow_head=False),
            web.get(f"{prefix}/conformance", self.conformance, allow_head=False),
            # Processes
            web.get(f"{prefix}/processes/", self.list_processes, allow_head=False),
            web.get(f"{prefix}/processes", redirect_trailing_slash(), allow_head=False),
            web.get(f"{prefix}/processes/{{Ident}}", self.describe_process, allow_head=False),
            web.post(f"{prefix}/processes/{{Ident}}/execution", self.execute_process),
            # Jobs
            web.get(f"{prefix}/jobs/", self.list_jobs, allow_head=False),
            web.get(f"{prefix}/jobs", redirect_trailing_slash(), allow_head=False),
        ]

        if self._enable_ui:
            _routes.extend(
                (
                    # Jobs UI
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
                ),
            )

        _routes.extend(
            (
                # Jobs
                web.get(f"{prefix}/jobs/{{JobId}}", self.job_status, allow_head=False),
                web.delete(f"{prefix}/jobs/{{JobId}}", self.dismiss_job),
                web.get(f"{prefix}/jobs/{{JobId}}/results", self.job_results, allow_head=False),
                # Log
                web.get(f"{prefix}/jobs/{{JobId}}/log", self.job_log, allow_head=False),
                # Files
                web.get(
                    f"{prefix}/jobs/{{JobId}}/files",
                    redirect_trailing_slash(),
                    allow_head=False,
                ),
                web.get(f"{prefix}/jobs/{{JobId}}/files/", self.job_files, allow_head=False),
                web.get(f"{prefix}/jobs/{{JobId}}/files/{{Resource:.+}}", self.job_download),
                # Services
                web.get(f"{prefix}/services/", self.list_services, allow_head=False),
                web.get(f"{prefix}/services", redirect_trailing_slash(), allow_head=False),
            ),
        )

        return _routes

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
        """Get known service name from request"""
        service = self._accesspolicy.get_service(request)
        if raise_error and not self._executor.known_service(service):
            ErrorResponse.raises(web.HTTPServiceUnavailable, "Service not known")
        return service

    def get_project(self, request: web.Request) -> Optional[str]:
        project = self._accesspolicy.get_project(request)
        # Ensure that project starts with '/'
        if project and not project.startswith("/"):
            project = f"/{project}"
        return project
