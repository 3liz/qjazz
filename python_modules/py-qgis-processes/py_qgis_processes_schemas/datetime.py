from pydantic import (
    Field,
)

from typing_extensions import (
    Annotated
)


DateTime = Annotated[
    datetime.datetime,

]


Date = Annotated[
    datetime.date

]

Time = Annotated[
    datetime.time

]

