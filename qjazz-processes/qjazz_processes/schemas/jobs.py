#
# See https://github.com/opengeospatial/ogcapi-processes/
#

from datetime import datetime
from typing import (
    ClassVar,
    Literal,
    TypeAlias,
)

from pydantic import JsonValue, TypeAdapter

from .models import (
    Field,
    JsonModel,
    LinkHttp,
    Option,
    OutputFormat,
)

DateTime = TypeAdapter(datetime)


class JobException(JsonModel):
    type_: str = Field(alias="type")
    title: Option[str] = None
    status: Option[int] = None
    detail: Option[str] = None
    instance: Option[str] = None


#
# Note: the 'pending' state is not part of OGC standards,
# It indicates that a job has been queued for processing
# but not accepted by any worker.
#


JobStatusCode = Literal[
    "pending",
    "accepted",
    "running",
    "successful",
    "failed",
    "dismissed",
]


class JobStatus(JsonModel):
    """Conform to OGC api

    See /openapi/schemas/processes-core/statusInfo.yaml
    """

    PENDING: ClassVar[str] = "pending"
    ACCEPTED: ClassVar[str] = "accepted"
    RUNNING: ClassVar[str] = "running"
    SUCCESS: ClassVar[str] = "successful"
    FAILED: ClassVar[str] = "failed"
    DISMISSED: ClassVar[str] = "dismissed"

    # Attributes
    job_id: str = Field(title="Job ID")
    process_id: Option[str] = Field(title="Process ID")
    process_type: Literal["process"] = Field(
        title="Job type",
        default="process",
        alias="type",
    )
    status: JobStatusCode
    message: Option[str] = None
    created: datetime
    started: Option[datetime] = None
    finished: Option[datetime] = None
    updated: Option[datetime] = None
    progress: Option[int] = Field(ge=0, le=100)

    exception: Option[JobException] = None

    links: list[LinkHttp] = Field([])

    #
    # Extra
    #

    # Run configuraton
    run_config: Option[JsonValue] = None

    # Expiration timestamp
    expires_at: Option[datetime] = None


class Output(JsonModel):
    format: OutputFormat


class JobExecute(JsonModel):
    inputs: dict[str, JsonValue] = Field(default={})
    outputs: dict[str, Output] = Field(default={})


JobResults: TypeAlias = dict[str, JsonValue]
