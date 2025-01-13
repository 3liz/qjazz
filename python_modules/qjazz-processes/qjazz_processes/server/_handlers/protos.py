from pathlib import Path
from typing import Optional, Protocol

from aiohttp import web
from pydantic import TypeAdapter

from ...worker.exceptions import (
    ProcessNotFound,
    ProjectRequired,
)
from .. import swagger
from ..accesspolicy import AccessPolicy
from ..executor import (
    Executor,
    InputValueError,
    JobExecute,
    JobResults,
    JobStatus,
    JsonDict,
    PresenceDetails,
    ProcessDescription,
    ProcessFiles,
    ProcessLog,
    ProcessSummary,
    RunProcessException,
)
from ..jobrealm import JOB_REALM_HEADER, JobRealmConfig
from ..models import ErrorResponse
from ..storage import StorageConfig
from ..utils import Link, href, make_link, public_url

JOB_ID_HEADER = "X-Job-Id"

swagger.model(JobExecute)
swagger.model(JobStatus)
swagger.model(ProcessDescription)


JobResultsAdapter = TypeAdapter(JobResults)

swagger.model(JobResultsAdapter, "JobResults")


class HandlerProto(Protocol):
    _executor: Executor
    _accesspolicy: AccessPolicy
    _timeout: int
    _staticpath: Path
    _jobrealm: JobRealmConfig
    _storage: StorageConfig

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
        *,
        query: Optional[str] = None,
    ) -> str:
        ...
