""" Wrapper around Qgsserver
"""
from typing import (
    Optional,
    Protocol,
)

from qgis.core import QgsProject
from qgis.server import (
    QgsServer,
    QgsServerRequest,
    QgsServerResponse,
)

from .qgis_init import init_qgis_server


class Server(Protocol):

    use_default_handler: bool

    ApiNotFoundError: type[Exception]
    ProjectRequired: type[Exception]
    InternalError: type[Exception]

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
        """ Create a  QgsServer
        """
        inner = init_qgis_server(**kwargs)
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
