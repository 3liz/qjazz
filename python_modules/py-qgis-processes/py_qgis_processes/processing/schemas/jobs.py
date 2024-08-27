#
# See https://github.com/opengeospatial/ogcapi-processes/
#

from datetime import datetime

from pydantic import Field, JsonValue, TypeAdapter
from typing_extensions import (
    ClassVar,
    Dict,
    List,
    Literal,
    Optional,
    TypeAlias,
)

from .models import JsonModel, LinkHttp, OutputFormat

DateTime = TypeAdapter(datetime)


class JobException(JsonModel):
    type_: str = Field(alias='type')
    title: Optional[str] = None
    status: Optional[int] = None
    detail: Optional[str] = None
    instance: Optional[str] = None

#
# Note: the 'pending' state is not part of OGC standards,
# It indicates that a job has been queued for processing
# but not accepted by any worker.
#


JobStatusCode = Literal[
    'pending',
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
    PENDING: ClassVar[str] = 'pending'
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
    created: datetime
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    updated: Optional[datetime] = None
    progress: Optional[int] = Field(default=None, ge=0, le=100)

    exception: Optional[JobException] = None

    links: List[LinkHttp] = Field([])

    #
    # Extra
    #

    # Run configuraton
    run_config: Optional[JsonValue] = None

    # Expiration timestamp
    expires_at: Optional[datetime] = None


class Output(JsonModel):
    format: OutputFormat


class JobExecute(JsonModel):
    inputs: Dict[str, JsonValue] = Field(default={})
    outputs: Dict[str, Output] = Field(default={})


JobResults: TypeAlias = Dict[str, JsonValue]
