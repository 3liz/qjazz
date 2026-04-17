#
# No binding server wrapper
#
from typing import Optional, Self

from qgis.core import QgsProject
from qgis.server import (
    QgsServer,
    QgsServerRequest,
    QgsServerResponse,
)

from ..condition import assert_not_none


class ApiNotFoundError(Exception):  # type: ignore [no-redef]
    pass


class ProjectRequired(Exception):  # type: ignore [no-redef]
    pass


class InternalError(Exception):  # type: ignore [no-redef]
    pass


class ServerWrapper:
    ApiNotFoundError = ApiNotFoundError
    ProjectRequired = ProjectRequired
    InternalError = InternalError

    def __init__(self, inner: QgsServer):
        self._inner = inner

    def handle_request(
        self,
        request: QgsServerRequest,
        response: QgsServerResponse,
        project: Optional[QgsProject] = None,
        api: Optional[str] = None,
    ):
        if api:
            # Find the api
            iface = assert_not_none(self._inner.serverInterface())
            if not assert_not_none(iface.serviceRegistry()).getApi(api):
                raise ApiNotFoundError(api)
        elif not project:
            # Project is mandatory
            raise ProjectRequired()

        self._inner.handleRequest(request, response, project)

    @property
    def inner(self) -> QgsServer:
        return self._inner

    @classmethod
    def new(cls, **kwargs) -> Self:
        # Dummy method for making mypy happy
        raise NotImplementedError()
