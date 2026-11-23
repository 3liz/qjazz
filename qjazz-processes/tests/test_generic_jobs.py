"""Test process descriptions generated from generic jobs"""

from typing import Annotated, Any, Literal

import pytest

from qjazz_core.celery import CeleryConfig

from qjazz_processes.schemas import Field, JsonModel, Option
from qjazz_processes.schemas.processes import MetadataValue, ProcessDescription
from qjazz_processes.worker.celery import Job, JobContext, Worker
from qjazz_processes.worker.generic import (
    GenericJob,
    describe_process,
    list_processes,
)

#
# Test jobs
#

UserName = Annotated[str, Field(title="User name", description="The user name")]

OptionalArg = Annotated[
    Option[str],
    Field(title="An optional field", description="Optional description"),
]

ReturnValue = Annotated[str, Field(title="Return value", description="A string")]


class InnerArg(JsonModel):
    x: int


class ComplexArg(JsonModel):
    """A complex argument

    This is a more complex argument
    """

    flag: Literal["One", "Two"] = Field(default="One", title="Flag")
    inner: InnerArg


class ComplexReturnValue(JsonModel):
    """A complex return value"""

    num: int = Field(title="A number")
    val: str = Field(title="A string")


METADATA = [{"role": "test", "title": "Test metadata", "value": "foobar"}]


@pytest.fixture(scope="module")
def app() -> Worker:
    app = Worker("test_generic", CeleryConfig())

    @app.job(name="gen_simple", bind=True, run_context=True, base=GenericJob)
    def simple(
        self: GenericJob,
        ctx: JobContext,
        /,
        name: UserName,
        optional_arg: OptionalArg = None,
        count: int = 3,
    ) -> ReturnValue:
        """Simple task
        An example of generic task

        with a multiline description
        """
        return "ok"

    @app.job(name="gen_complex", bind=True, base=GenericJob, metadata=METADATA)
    def complex_(
        self: GenericJob,
        name: UserName,
        complex_arg: ComplexArg,
        *args: Any,
        **kwargs: Any,
    ) -> ComplexReturnValue:
        """Complex task"""
        return ComplexReturnValue(num=3, val="three")

    @app.job(name="gen_nodoc", base=GenericJob)
    def nodoc(*, value: int) -> None:
        pass

    @app.job(name="gen_model_default", base=GenericJob)
    def model_default(
        arg: ComplexArg = ComplexArg(inner=InnerArg(x=1)),  # noqa: B008
    ) -> None:
        pass

    # Instanciate tasks: this will build the processes descriptions
    app.finalize()
    return app


#
# Tests
#


def test_generic_jobs_registered(app: Worker) -> None:
    for ident in ("gen_simple", "gen_complex", "gen_nodoc"):
        assert ident in Job.RUN_CONFIGS
        assert isinstance(Job.RUN_CONFIGS[ident], ProcessDescription)
        # Job name is registered without the service prefix
        assert f"test_generic.{ident}" in app.tasks
        assert f"test_generic.{ident}" not in Job.RUN_CONFIGS


def test_generic_job_title_and_description(app: Worker) -> None:
    p = Job.RUN_CONFIGS["gen_simple"]
    assert p.id_ == "gen_simple"
    assert p.title == "Simple task"
    assert p.description == "An example of generic task\n\nwith a multiline description"
    assert p.metadata == ()


def test_generic_job_no_docstring(app: Worker) -> None:
    p = Job.RUN_CONFIGS["gen_nodoc"]
    # Title defaults to the function qualified name
    assert p.title.endswith("nodoc")
    assert p.description == ""


def test_generic_job_inputs(app: Worker) -> None:
    inputs = Job.RUN_CONFIGS["gen_simple"].inputs

    # Positional only arguments ('self', 'ctx') are not inputs
    assert list(inputs) == ["name", "optional_arg", "count"]

    name = inputs["name"]
    assert name.title == "User name"
    assert name.description == "The user name"
    assert name.schema_ == {"type": "string"}

    optional_arg = inputs["optional_arg"]
    assert optional_arg.title == "An optional field"
    assert optional_arg.description == "Optional description"
    assert optional_arg.schema_["type"] == "string"
    assert optional_arg.schema_["default"] is None

    count = inputs["count"]
    assert count.title == ""
    assert count.schema_ == {"type": "integer", "default": 3}


def test_generic_job_var_args_excluded(app: Worker) -> None:
    inputs = Job.RUN_CONFIGS["gen_complex"].inputs
    assert list(inputs) == ["name", "complex_arg"]


def test_generic_job_complex_input(app: Worker) -> None:
    complex_arg = Job.RUN_CONFIGS["gen_complex"].inputs["complex_arg"]
    assert complex_arg.title == "ComplexArg"
    assert complex_arg.description == "A complex argument\n\nThis is a more complex argument"

    schema = complex_arg.schema_
    assert schema["type"] == "object"
    assert schema["required"] == ["inner"]
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert properties["flag"] == {
        "default": "One",
        "enum": ["One", "Two"],
        "title": "Flag",
        "type": "string",
    }
    assert properties["inner"] == {"$ref": "#/$defs/InnerArg"}
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    assert "InnerArg" in defs


def test_generic_job_simple_output(app: Worker) -> None:
    outputs = Job.RUN_CONFIGS["gen_simple"].outputs
    assert list(outputs) == ["output"]

    output = outputs["output"]
    assert output.title == "Return value"
    assert output.description == "A string"
    assert output.schema_ == {"type": "string"}


def test_generic_job_complex_output(app: Worker) -> None:
    output = Job.RUN_CONFIGS["gen_complex"].outputs["output"]
    assert output.title == "ComplexReturnValue"
    assert output.description == "A complex return value"
    assert output.schema_["type"] == "object"
    properties = output.schema_["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"num", "val"}
    assert output.schema_["required"] == ["num", "val"]


def test_generic_job_no_return_annotation(app: Worker) -> None:
    assert Job.RUN_CONFIGS["gen_nodoc"].outputs == {}


def test_generic_job_metadata(app: Worker) -> None:
    metadata = Job.RUN_CONFIGS["gen_complex"].metadata
    assert len(metadata) == 1
    assert isinstance(metadata[0], MetadataValue)
    assert metadata[0].role == "test"
    assert metadata[0].title == "Test metadata"
    assert metadata[0].value == "foobar"


def test_generic_job_missing_annotation() -> None:
    app = Worker("test_generic_bad", CeleryConfig())

    @app.job(name="gen_bad", base=GenericJob)
    def bad(value) -> None:  # type: ignore [no-untyped-def]  # noqa: ANN001 (tested)
        pass

    with pytest.raises(TypeError, match="Missing annotation for argument value"):
        app.finalize()

    assert "gen_bad" not in Job.RUN_CONFIGS


#
# Inspect commands
#


def test_generic_list_processes(app: Worker) -> None:
    processes = {p["id"]: p for p in list_processes(None)}
    assert {"gen_simple", "gen_complex", "gen_nodoc"} <= set(processes)

    p = processes["gen_complex"]
    assert p["title"] == "Complex task"
    assert p["metadata"] == METADATA
    # Summary does not include inputs/outputs
    assert "inputs" not in p
    assert "outputs" not in p


def test_generic_describe_process(app: Worker) -> None:
    p = describe_process(None, "gen_simple", None)
    assert p is not None
    assert p["id"] == "gen_simple"
    assert p["title"] == "Simple task"
    assert p["jobControlOptions"] == ["sync-execute", "async-execute", "dismiss"]
    assert list(p["inputs"]) == ["name", "optional_arg", "count"]
    assert p["inputs"]["name"]["schema"] == {"type": "string"}
    assert p["inputs"]["name"]["minOccurs"] == 1
    assert p["outputs"]["output"]["schema"] == {"type": "string"}
    # Validate round trip
    ProcessDescription.model_validate(p)


def test_generic_describe_unknown_process(app: Worker) -> None:
    assert describe_process(None, "gen_unknown", None) is None


def test_generic_job_complex_default(app: Worker) -> None:
    """Test that a model default is serialized as json in the input schema"""
    arg = Job.RUN_CONFIGS["gen_model_default"].inputs["arg"]
    assert arg.schema_["default"] == {"flag": "One", "inner": {"x": 1}}
    # Having a default does not make the input optional
    assert arg.min_occurs == 1
