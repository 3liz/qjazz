from datetime import datetime
from typing import (
    Literal,
    Optional,
    Sequence,
    TypedDict,
)

from pydantic import Field, TypeAdapter

from ..schemas import JsonModel, Link, LinkHttp

LinkSequence: TypeAdapter = TypeAdapter(Sequence[LinkHttp])


class WorkerVersion1(JsonModel):
    version: Literal[1] = 1


class WorkerPresenceV1(WorkerVersion1):
    service: str
    title: str
    description: str
    links: Sequence[LinkHttp]
    online_since: float
    qgis_version_info: int
    versions: str | Sequence[str]
    result_expires: int
    callbacks: Sequence[str] = Field([])


WorkerPresenceVersion = WorkerPresenceV1
WorkerPresence = WorkerPresenceV1


class ProcessLogV1(WorkerVersion1):
    timestamp: datetime
    log: str


ProcessLogVersion = ProcessLogV1
ProcessLog = ProcessLogV1


class ProcessFilesVersionV1(WorkerVersion1):
    links: Sequence[Link]


ProcessFilesVersion = ProcessFilesVersionV1
ProcessFiles = ProcessFilesVersionV1


class JobMeta(TypedDict):
    created: str
    realm: Optional[str]
    service: str
    process_id: str
    expires: int
    tag: Optional[str]
