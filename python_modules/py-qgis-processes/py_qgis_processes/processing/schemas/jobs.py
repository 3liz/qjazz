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

from .models import (
    JsonModel,
    LinkHttp,
    Null,
    NullField,
    OutputFormat,
)

DateTime = TypeAdapter(datetime)


class JobException(JsonModel):
    type_: str = Field(alias='type')
    title: Optional[str] = Null
    status: Optional[int] = Null
    detail: Optional[str] = Null
    instance: Optional[str] = Null

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
    process_id: Optional[str] = NullField(title="Process ID")
    process_type: Literal['process'] = Field(
        title="Job type",
        default="process",
        alias='type',
    )
    status: JobStatusCode
    message: Optional[str] = Null
    created: datetime
    started: Optional[datetime] = Null
    finished: Optional[datetime] = Null
    updated: Optional[datetime] = Null
    progress: Optional[int] = NullField(ge=0, le=100)

    exception: Optional[JobException] = Null

    links: List[LinkHttp] = Field([])

    #
    # Extra
    #

    # Run configuraton
    run_config: Optional[JsonValue] = Null

    # Expiration timestamp
    expires_at: Optional[datetime] = Null


class Output(JsonModel):
    format: OutputFormat


class JobExecute(JsonModel):
    inputs: Dict[str, JsonValue] = Field(default={})
    outputs: Dict[str, Output] = Field(default={})


JobResults: TypeAlias = Dict[str, JsonValue]
