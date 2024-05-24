#
# See https://github.com/opengeospatial/ogcapi-processes/
#

from datetime import datetime

from pydantic import Field, JsonValue, TypeAdapter
from typing_extensions import (
    ClassVar,
    Dict,
    Literal,
    Optional,
    Sequence,
    TypeAlias,
)

from .models import JsonModel, Link, OutputFormat

DateTime = TypeAdapter(datetime)


class JobException(JsonModel):
    type_: str = Field(alias='type')
    title: Optional[str] = None
    status: Optional[int] = None
    detail: Optional[str] = None
    instance: Optional[str] = None


JobStatusCode = Literal[
    'accepted',
    'running',
    'successful',
    'failed',
    'dismissed',
]


class JobStatus(JsonModel):
    """ Conform to OGC api

        See /openapi/schemas/processes-core/statusInfo.yaml
    """
    ACCEPTED: ClassVar[str] = 'accepted'
    RUNNING: ClassVar[str] = 'running'
    SUCCESS: ClassVar[str] = 'successful'
    FAILED: ClassVar[str] = 'failed'
    DISMISSED: ClassVar[str] = 'dismissed'

    # Attributes
    job_id: str = Field(title="Job ID")
    process_id: Optional[str] = Field(default=None, title="Process ID")
    process_type: Literal['process'] = Field(
        title="Job type",
        default="process",
        alias='type',
    )
    status: JobStatusCode
    message: Optional[str] = None
    created: Optional[datetime] = None
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    updated: Optional[datetime] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)

    exception: JobException

    links: Sequence[Link] = ()


class Output(JsonModel):
    format: OutputFormat


class JobExecute(JsonModel):
    inputs: Dict[str, JsonValue]
    outputs: Dict[str, Output]


JobResults: TypeAlias = Dict[str, JsonValue]
