import re

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePosixPath

import tornado.httputil

from tornado.web import HTTPError
from typing_extensions import Optional

from py_qgis_contrib.core import logger


class Routable(ABC):

    @property
    @abstractmethod
    def request(self) -> tornado.httputil.HTTPServerRequest:
        """ Return the server Request
        """
        ...

    @abstractmethod
    def get_route(self) -> str:
        """ Return the route from the original request path
        """


@dataclass
class Route:
    route: str
    project: Optional[str] = None
    api: Optional[str] = None
    path: str = '/'  # API path


class RouterBase(ABC):

    @abstractmethod
    def route(self, routable: Routable) -> Route:
        """ Return a `Route` object from the request object
        """
        ...

#
# The default router
#
# A project may be specified by (in precedence order):
#
# 1. A path element followed by `/_/`, the path element will be included
#    in the returned urls
# 2. A `MAP` query argument: the `MAP` will be part of the returned urls
# 3. A `X-Qgis-Project` Header, the project will not appears in returned url's
#


class DefaultRouter(RouterBase):
    """
    This router will extract routing
    informations from the request

    According the following rules:

    * Any url with `SERVICE` parameter is routed
       as OWS request (as required by Qgis).
       If the project is not defined as `MAP` parameter
       or as `X-Qgis-Project` header, we take the relative path from
       the route in the request path.
    * `<channel_route>/(?:<project_path>/_/)(/<api_path>)` is routed
       os API request
    """
    API_MATCH = re.compile(r'(?:(.+)/_/)?([^\/]+)(/.*)?')

    def route(self, routable: Routable) -> Route:
        # Get the route from the request path
        route = routable.get_route()
        if not route:
            raise HTTPError(404)

        req = routable.request

        logger.trace("DefaultRouter::route for %s (route: %s)", req.uri, route)

        # Get the project
        project = req.arguments.get('MAP')
        if project:
            project = project[0].decode()
        else:
            project = req.headers.get('X-Qgis-Project')

        if req.arguments.get('SERVICE') is not None:
            # OWS project
            if not project:
                # Check project in the path
                project = PurePosixPath(req.path).relative_to(route)
                project = f"/{project}"

            logger.trace("DefaultRouter::router %s OWS request detected", req.uri)
            return Route(route=route, project=project)
        else:
            # Check project in request path
            path = str(PurePosixPath(req.path).relative_to(route).as_posix())
            if path == '.':
                path = ""
            m = self.API_MATCH.match(path)
            if not m:
                raise HTTPError(400, reason="Missing api specification")
            _project, api, api_path = m.groups()
            logger.trace(
                "DefaultRouter::router %s API request detected (project %s, api: %s, path: %s)",
                req.uri,
                _project,
                api,
                api_path
            )
            if project and _project:
                logger.error("Multiple project definitions in '%s'", req.full_url())
                raise HTTPError(400, reason="Multiple project definitions in request")
            elif not project:
                project = f"/{_project}"

            return Route(route=route, project=project, api=api, path=api_path)
