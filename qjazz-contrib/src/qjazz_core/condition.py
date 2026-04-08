#
# Define pre/post condition assertion
#
from typing import Any, NoReturn, Optional

from .errors import QJazzException


class PreconditionError(QJazzException):
    pass


class PostconditionError(QJazzException):
    pass


def assert_precondition(condition: bool, message: Optional[str] = None):
    if not condition:
        raise PreconditionError(message or "Pre condition failed")


def assert_postcondition(condition: bool, message: Optional[str] = None):
    if not condition:
        raise PostconditionError(message or "Post condition failed")


def assert_unreachable(value: Any) -> NoReturn:
    raise AssertionError(f"Expected unreachable code: {value}")
