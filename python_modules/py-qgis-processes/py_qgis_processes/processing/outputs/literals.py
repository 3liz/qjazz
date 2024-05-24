

from .base import OutputParameter


class OutputBoolean(OutputParameter):
    _ValueType = bool


class OutputString(OutputParameter):
    _ValueType = str


class OutputNumber(OutputParameter):
    _ValueType = float
