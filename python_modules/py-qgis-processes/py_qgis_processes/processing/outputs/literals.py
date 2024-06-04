

from .base import OutputParameter


class OutputBoolean(OutputParameter):
    _Model = bool


class OutputString(OutputParameter):
    _Model = str


class OutputNumber(OutputParameter):
    _Model = float
