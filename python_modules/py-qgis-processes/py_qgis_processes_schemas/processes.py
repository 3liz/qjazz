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

from .models import JsonModel, Link, LinkHttp, NullField


class MetadataLink(Link):
    role: Optional[str] = NullField()


class MetadataValue(JsonModel):
    role: Optional[str] = NullField()
    title: Optional[str] = NullField()
    lang: Optional[str] = NullField()
    value: Optional[JsonValue]

#
# Metadata
#


Metadata = Annotated[
    MetadataLink | MetadataValue,
    Field(union_mode='left_to_right'),
]


class DescriptionType(JsonModel):
    title: str = ""
    description: Optional[str] = NullField()
    keywords: Sequence[str] = ()
    metadata: Sequence[Metadata] = ()


#
# IO descriptions
#
# See openapi/schemas/processes-core
#

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


class ProcessesSummary(DescriptionType):
    id_: str = Field(alias="id", title="Process id")
    version: str
    job_control_options: Sequence[JobControlOptions] = (
        'sync-execute',
        'async-execute',
        'dismiss',
    )
    links: Sequence[LinkHttp] = Field(default=[])


class ProcessesDescription(ProcessesSummary):
    inputs: Dict[str, InputDescription] = Field(default={})
    outputs: Dict[str, OutputDescription] = Field(default={})


# Adapter for process Summary list
ProcessSummaryList = TypeAdapter(Sequence[ProcessesSummary])
