#
# OGC schema models
# See https://github.com/opengeospatial/ogcapi-processes/blob/master/openapi/schemas
#

from pydantic import (
    Field,
    JsonValue,
)
from typing_extensions import (
    Annotated,
    Dict,
    Literal,
    Optional,
    Sequence,
)

from .models import JsonModel, Link


class MetadataLink(Link):
    role: Optional[str] = None


class MetadataValue(JsonModel):
    role: Optional[str] = None
    title: Optional[str] = None
    lang: Optional[str] = None
    value: Optional[JsonValue] = None

#
# Metadata
#


Metadata = Annotated[
    MetadataLink | MetadataValue,
    Field(union_mode='left_to_right'),
]


class DescriptionType(JsonModel):
    title: str = ""
    description: Optional[str] = None
    keywords: Sequence[str] = ()
    metadata: Optional[Metadata] = None


#
# IO descriptions
#
# See openapi/schemas/processes-core
#

_NonZeroPositiveInt = Annotated[int, Field(gt=0)]


ValuePassing = Sequence[Literal["byValue", "byReference"]]


class InputDescription(DescriptionType):
    schema_: JsonValue = Field(alias="schema")
    value_passing: ValuePassing = ('byValue',)
    min_occurs: _NonZeroPositiveInt = 1
    max_occurs: _NonZeroPositiveInt | Literal["unbounded"] = 1


class OutputDescription(DescriptionType):
    schema_: JsonValue = Field(alias="schema")


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
    links: Sequence[Link] = Field(default=[])


class ProcessesDescription(ProcessesSummary):
    inputs: Dict[str, InputDescription]
    outputs: Dict[str, OutputDescription]
