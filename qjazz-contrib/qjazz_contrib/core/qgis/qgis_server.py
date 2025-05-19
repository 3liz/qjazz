"""Wrapper around Qgsserver"""

from typing import (
    Optional,
    Protocol,
    TypeVar,
)

from qgis.core import QgsProject
from qgis.server import (
    QgsServer,
    QgsServerRequest,
    QgsServerResponse,
)

from .qgis_init import init_qgis_server

E = TypeVar("E", bound=Exception)


class Server(Protocol[E]):
    ApiNotFoundError: E
    ProjectRequired: E
    InternalError: E

    @property
    def inner(self) -> QgsServer: ...

    def handle_request(
        self,
        request: QgsServerRequest,
        response: QgsServerResponse,
        project: Optional[QgsProject] = None,
        api: Optional[str] = None,
    ): ...

    @classmethod
    def new(cls, **kwargs) -> "Server":
        """Create a  QgsServer"""
        inner = init_qgis_server(**kwargs)
        try:
            from .qgis_binding import (
                ApiNotFoundError,
                InternalError,
                ProjectRequired,
                Server,
            )

            cls.ApiNotFoundError = ApiNotFoundError
            cls.ProjectRequired = ProjectRequired
            cls.InternalError = InternalError
            return Server(inner)
        except ModuleNotFoundError:
            from .no_binding import ServerWrapper

            return ServerWrapper(inner)
