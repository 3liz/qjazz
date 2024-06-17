from aiohttp import web
from pydantic import TypeAdapter
from typing_extensions import Optional, Protocol

from ...executor import (  # noqa F401
    Executor,
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    PresenceDetails,
    ProcessDescription,
    ProcessSummary,
)
from .. import swagger  # noqa F401
from ..accesspolicy import AccessPolicy
from ..cache import ProcessesCache
from ..jobrealm import JOB_REALM_HEADER, get_job_realm, job_realm  # noqa F401
from ..models import ErrorResponse  # noqa F401
from ..utils import Link, href, make_link, public_url  # noqa F401

swagger.model(JobExecute)
swagger.model(JobStatus)


JobResultsAdapter = TypeAdapter(JobResults)

swagger.model(JobResultsAdapter, "JobResults")


class HandlerProto(Protocol):
    _executor: Executor
    _accesspolicy: AccessPolicy
    _timeout: int
    _cache: ProcessesCache

    def get_service(self, request: web.Request, raise_error: bool = True) -> str:
        ...

    def get_project(self, request: web.Request) -> Optional[str]:
        ...

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
        project: Optional[str] = None,
    ) -> str:
        ...
