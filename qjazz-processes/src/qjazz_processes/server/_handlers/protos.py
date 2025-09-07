from pathlib import Path
from typing import Optional, Protocol

from aiohttp import web
from pydantic import TypeAdapter, ValidationError
from qjazz_store import StoreCreds

from ...worker.exceptions import (
    ProcessNotFound,
    ProjectRequired,
    ServiceNotAvailable,
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
from ..models import BoolParam, ErrorResponse
from ..storage import StorageConfig
from ..store import StoreConfig
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
    _store: Optional[StoreConfig]
    _enable_ui: bool

    def get_service(self, request: web.Request) -> str: ...

    def get_project(self, request: web.Request) -> Optional[str]: ...

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
        project: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> str: ...

    def get_identity(self, req: web.Request) -> str: ...

    async def store_creds(self) -> StoreCreds: ...


def validate_param[T](adapter: TypeAdapter[T], request: web.Request, name: str, default: T) -> T:
    """Validate query param"""
    try:
        return adapter.validate_python(request.query.get(name, default))
    except ValidationError as err:
        raise web.HTTPBadRequest(
            content_type="application/json",
            text=err.json(include_context=False, include_url=False),
        )
