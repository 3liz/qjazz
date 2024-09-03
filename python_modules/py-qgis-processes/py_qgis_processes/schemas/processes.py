#
# OGC schema models
# See https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas
#

from pydantic import (
    Field,
    JsonValue,
    TypeAdapter,
)
from typing_extensions import (
    Annotated,
    Dict,
    Literal,
    Optional,
    Sequence,
)

from .models import (
    JsonModel,
    Link,
    LinkHttp,
    Null,
)


class MetadataLink(Link):
    role: Optional[str] = Null


class MetadataValue(JsonModel):
    role: Optional[str] = Null
    title: Optional[str] = Null
    lang: Optional[str] = Null
    value: Optional[JsonValue]

#
# Metadata
#


Metadata = Annotated[
    MetadataLink | MetadataValue,
    Field(union_mode='left_to_right'),
]


#
# IO descriptions
#
# See openapi/schemas/processes-core
#

class DescriptionType(JsonModel):
    title: str = ""
    description: Optional[str] = Null
    keywords: Sequence[str] = ()
    metadata: Sequence[Metadata] = ()


_NonZeroPositiveInt = Annotated[int, Field(gt=0)]
_PositiveInt = Annotated[int, Field(ge=0)]

ValuePassing = Sequence[Literal["byValue", "byReference"]]


class InputDescription(DescriptionType):
    schema_: JsonValue = Field(alias="schema")
    value_passing: ValuePassing = ('byValue',)
    min_occurs: _PositiveInt = 1
    max_occurs: _NonZeroPositiveInt | Literal["unbounded"] = 1


class OutputDescription(DescriptionType):
    schema_: JsonValue = Field(alias="schema")
    value_passing: ValuePassing = ('byValue',)


#
# Processes
#

JobControlOptions = Literal['sync-execute', 'async-execute', 'dismiss']


class ProcessSummary(DescriptionType):
    id_: str = Field(alias="id", title="Process id")
    version: str
    job_control_options: Sequence[JobControlOptions] = (
        'sync-execute',
        'async-execute',
        'dismiss',
    )
    links: Sequence[LinkHttp] = Field(default=[])


class ProcessDescription(ProcessSummary):
    inputs: Dict[str, InputDescription] = Field(default={})
    outputs: Dict[str, OutputDescription] = Field(default={})


# Adapter for process Summary list
ProcessSummaryList: TypeAdapter = TypeAdapter(Sequence[ProcessSummary])
