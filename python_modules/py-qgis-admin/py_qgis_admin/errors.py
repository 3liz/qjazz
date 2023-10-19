
class ServiceException(Exception):
    pass


class ServiceNotAvailable(ServiceException):
    pass


class RequestArgumentError(ServiceException):
    def __init__(self, details):
        super().__init__(details)
        self.details = details
