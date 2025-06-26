from typing import (
    Annotated,
    Literal,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.celery import JobContext
from qjazz_processes.schemas import (
    Field,
    JsonModel,
    Option,
)
from qjazz_processes.worker.generic import (
    GenericJob,
    GenericWorker,
)

#
# Worker
#

class Worker(GenericWorker):

    #def on_worker_ready(self) -> None:
    #    "Set custom initialization"
    #    super().on_worker_ready()

    #def on_worker_shutdown(self) -> None:
    #    "Set custom shutdown
    #    super().on_worker_shutdown()

    pass


app = Worker()

OptionalArg = Annotated[
    Option[str],
    Field(
        title="An optional field",
        description="""
        Lorem ipsum dolor sit amet, consectetur adipiscing elit.
        Cras molestie felis lorem, eu pretium velit tincidunt non.
        Integer pharetra quam ac nibh rutrum commodo.
        """,
    ),
]

UserName = Annotated[str, Field(title="User name")]

ReturnValue = Annotated[str, Field(title="Return value")]


@app.job(name="first_task", bind=True, run_context=True, base=GenericJob)
def task_one(
    self: GenericJob,
    ctx: JobContext,
    /,
    name: UserName,
    optional_arg: OptionalArg = None,
) -> ReturnValue:
    """Task one
    An example of generic task
    """
    logger.info(
        "Executing task number one with arguments: (%s, %s)",
        name,
        optional_arg,
    )
    return "Task number one ok"


class ComplexArg(JsonModel):
    """A complex argument

    This is a more complex argument with many fields
    """
    flag: Literal["One", "Two"] = Field(default="One", title="Flag")
    value: str = Field(
        title="String",
        description="A literal string"
    )


class ComplexReturnValue(JsonModel):
    """ A complex return value

    This is a complex return value with many fields
    """
    num: int = Field(title="A number", description="A literal integer")
    val: str = Field(title="A string", description="A literal string")


@app.job(name="second_task", bind=True, run_context=True, base=GenericJob)
def task_two(
    self: GenericJob,
    ctx: JobContext,
    /,
    name: UserName,
    complex_arg: ComplexArg,
) -> ComplexReturnValue:
    """Task two
    An example of generic task
    """
    logger.info(
        "Executing task number two with arguments: (%s, %s)",
        name,
        complex_arg,
    )

    return ComplexReturnValue(num=3, val="Here is a number three")


