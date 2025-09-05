
from qjazz_core.errors import QJazzException


class InvalidCacheRootUrl(QJazzException):
    pass


class ResourceNotAllowed(QJazzException):
    pass


class StrictCheckingFailure(QJazzException):
    pass


class UnreadableResource(QJazzException):
    """Indicates that the ressource exists but is not readable"""
    pass
