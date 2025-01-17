

class InvalidCacheRootUrl(Exception):
    pass


class ResourceNotAllowed(Exception):
    pass


class StrictCheckingFailure(Exception):
    pass


class UnreadableResource(Exception):
    """ Indicates that the  ressource exists but is not readable
    """
    pass
