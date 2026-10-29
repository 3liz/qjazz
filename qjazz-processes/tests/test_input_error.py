import json

import pytest

from celery import Celery
from pydantic import TypeAdapter, ValidationError

from qjazz_processes.schemas import InputValueError


def _validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        TypeAdapter(int).validate_python("not a number")
    return exc_info.value


def test_input_error_message():
    """Plain message produces a valid json body"""
    msg = 'Processing parameters error:\nIncorrect "value" for PARAM'
    err = InputValueError(msg)

    assert json.loads(err.response) == {"message": msg}
    assert str(err) == msg


def test_input_error_details():
    """Validation details are included in the json body"""
    err = InputValueError("'PARAM' parameter error", _validation_error())

    body = json.loads(err.response)
    assert body["message"] == "'PARAM' parameter error"
    assert body["details"][0]["type"] == "int_parsing"
    # Input value must not be leaked
    assert "input" not in body["details"][0]
    assert json.loads(str(err)) == body


@pytest.mark.parametrize("with_details", [False, True])
def test_input_error_celery_roundtrip(with_details: bool):
    """Exception is recreated identically from Celery result backend"""
    details = _validation_error() if with_details else None
    err = InputValueError('Invalid "value"\nfor PARAM', details)

    backend = Celery().backend
    serialized = backend.prepare_exception(err, "json")
    # Must be json serializable
    serialized = json.loads(json.dumps(serialized))

    exc = backend.exception_to_python(serialized)
    assert isinstance(exc, InputValueError)
    assert exc.response == err.response
    assert str(exc) == str(err)

    body = json.loads(exc.response)
    assert body["message"] == 'Invalid "value"\nfor PARAM'
    assert ("details" in body) == with_details
