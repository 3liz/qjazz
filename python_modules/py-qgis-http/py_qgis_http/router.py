from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import unquote_plus

from aiohttp import web
from typing_extensions import Awaitable, Mapping, Optional, Protocol

from py_qgis_contrib.core import logger

from .webutils import _decode


class Routable(Protocol):

    @property
    def request(self) -> web.Request:
        """ Return the server Request
        """
        ...

    def get_route(self) -> str | None:
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
    def route(self, routable: Routable) -> Awaitable[Route]:
        """ Return a `Route` object from the request object
        """
        ...

    async def arguments(self, request: web.Request) -> Mapping[str, str]:
        args: Mapping
        if request.method == 'GET':
            args = request.query
        elif request.content_type.startswith('application/x-www-form-urlencoded') or \
            request.content_type.startswith('multipart/form-data'):
            args = await request.post()
        return args


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
    * `<channel_route>/(?:<project_path>/_/)(<api_path>)` is routed
       as API request
    """
    async def route(self, routable: Routable) -> Route:
        # Get the route from the request path
        route = routable.get_route()
        if not route:
            raise web.HTTPNotFound()

        request = routable.request

        logger.trace("DefaultRouter::route for %s (route: %s)", request.url, route)

        project: str | None

        args = await self.arguments(request)

        # Get the project
        map_arg = _decode('MAP', args.get('MAP', ''))
        if map_arg:
            project = unquote_plus(map_arg)
        else:
            project = request.headers.get('X-Qgis-Project')

        if args.get('SERVICE') is not None:
            # OWS project
            if not project:
                # Check project in the path
                project = request.path.removeprefix(route)

            logger.trace("DefaultRouter::router %s OWS request detected", request.url)
            return Route(route=route, project=project)
        else:
            # Check project in request path
            path = request.path.removeprefix(route)

            head, sep, tail = path.partition('/_/')
            if tail:
                # Handle {:project}/_/{:api_path} scheme
                if project:
                    # If the project is already defined with MAP or
                    # header: redirect to the project's location
                    logger.warning(
                        "Project's redefinition in url %s: sending redirection",
                        request.url,
                    )
                    raise web.HTTPFound(f"{route}{project}/_/{tail}")
                project = f"{head}"
                api, _, api_path = tail.partition('/')
            elif head and not sep:
                # Handle {:api_path} scheme
                api, _, api_path = head.partition('/')
            else:
                # Invalid path ending with '/_/'
                raise web.HTTPBadRequest(reason="Missing api specification")

            if api_path:
                api_path = f"/{api_path}"

            # Clean up suffixes from api name
            if api.endswith(".html"):
                api = api.removesuffix(".html")
            elif api.endswith(".json"):
                api = api.removesuffix(".json")

            logger.trace(
                "DefaultRouter::router %s API request detected (project %s, api: %s, path: %s)",
                request.url,
                project,
                api,
                api_path,
            )

            return Route(route=route, project=project, api=api, path=api_path)
