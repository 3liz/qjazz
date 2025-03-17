class ProcessesException(Exception):
    pass


class DismissedTaskError(ProcessesException):
    pass


class ServiceNotAvailable(ProcessesException):
    pass


class UnreachableDestination(ProcessesException):
    pass


class ProcessNotFound(ProcessesException):
    pass


class ProjectRequired(ProcessesException):
    pass
