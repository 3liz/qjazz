#
# OGC schema models
# See https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas
#

from typing import (
    Annotated,
    Literal,
    Optional,
    Sequence,
)

from pydantic import (
    Field,
    JsonValue,
    TypeAdapter,
)

from .models import (
    JsonModel,
    Link,
    LinkHttp,
    Option,
)


class MetadataLink(Link):
    role: Option[str] = None


class MetadataValue(JsonModel):
    role: Option[str] = None
    title: Option[str] = None
    lang: Option[str] = None
    value: Optional[JsonValue]


#
# Metadata
#


Metadata = Annotated[
    MetadataLink | MetadataValue,
    Field(union_mode="left_to_right"),
]


#
# IO descriptions
#
# See openapi/schemas/processes-core
#


class DescriptionType(JsonModel):
    title: str = ""
    description: Option[str] = None
    keywords: Sequence[str] = ()
    metadata: Sequence[Metadata] = ()


_NonZeroPositiveInt = Annotated[int, Field(gt=0)]
_PositiveInt = Annotated[int, Field(ge=0)]

ValuePassing = Sequence[Literal["byValue", "byReference"]]


class InputDescription(DescriptionType):
    schema_: dict[str, JsonValue] = Field(alias="schema")
    value_passing: ValuePassing = ("byValue",)
    min_occurs: _PositiveInt = 1
    max_occurs: _NonZeroPositiveInt | Literal["unbounded"] = 1


class OutputDescription(DescriptionType):
    schema_: dict[str, JsonValue] = Field(alias="schema")
    value_passing: ValuePassing = ("byValue",)


#
# Processes
#

JobControlOptions = Literal["sync-execute", "async-execute", "dismiss"]


class ProcessSummary(DescriptionType):
    id_: str = Field(alias="id", title="Process id")
    version: str = "n/a"
    job_control_options: Sequence[JobControlOptions] = (
        "sync-execute",
        "async-execute",
        "dismiss",
    )
    links: list[LinkHttp] = Field(default=[])


class ProcessDescription(ProcessSummary):
    inputs: dict[str, InputDescription] = Field(default={})
    outputs: dict[str, OutputDescription] = Field(default={})


# Adapter for process Summary list
ProcessSummaryList: TypeAdapter = TypeAdapter(Sequence[ProcessSummary])
