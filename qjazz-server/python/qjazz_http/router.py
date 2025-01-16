from abc import abstractmethod
from dataclasses import dataclass
from typing import (
    Annotated,
    Any,
    Awaitable,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Self,
    runtime_checkable,
)
from urllib.parse import unquote_plus

from aiohttp import web
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    ImportString,
    TypeAdapter,
    WithJsonSchema,
    model_validator,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.config import ConfigBase

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


@runtime_checkable
class RouterBase(Protocol):

    @abstractmethod
    def route(self, routable: Routable) -> Awaitable[Route]:
        """ Return a `Route` object from the request object
        """
        ...

    async def arguments(self, request: web.Request) -> Mapping:
        args: Mapping
        if request.method == 'GET':
            args = request.query
        elif request.method == 'POST' and \
        ( \
            request.content_type.startswith('application/x-www-form-urlencoded') or \
            request.content_type.startswith('multipart/form-data') \
        ):
            args = await request.post()
        else:
            args = request.query
        return args


#
#  Router configuration
#

def _parse_config_options(val: str | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(val, str):
        val = TypeAdapter(Dict[str, Any]).validate_json(val)
    return val


RouterConfigOptions = Annotated[
    Dict[str, Any],
    BeforeValidator(_parse_config_options),
]


class RouterConfig(ConfigBase):
    router_class: Annotated[
        ImportString,
        WithJsonSchema({'type': 'string'}),
        Field(
            default="qjazz_http.router.DefaultRouter",
            validate_default=True,
            title="The router class",
            description=(
                "The router class allow for defining routing rules\n"
                "from the request url."
            ),
        ),
    ]
    config: RouterConfigOptions = Field({}, title="Router configuration")

    @model_validator(mode='after')
    def validate_config(self) -> Self:

        klass = self.router_class

        if not issubclass(klass, RouterBase):
            raise ValueError(f"{klass} does not suppport ProtocolHandler protocol")

        self._router_conf: BaseModel | None = None
        if hasattr(klass, 'Config') and issubclass(klass.Config, BaseModel):
            self._handler_conf = klass.Config.model_validate(self.config)

        return self

    def create_instance(self) -> RouterBase:
        if self._router_conf:
            return self.router_class(self._handler_conf)
        else:
            return self.router_class()


#
# The default router
#
# A project may be specified by (in precedence order):
#
# 1. As last part of the path with OWS urls only.
# 2. With a `MAP` query argument: the `MAP` will be part of the returned urls
# 3. A `X-Qgis-Project` Header, the project will not appears in returned url's
#

def get_ows_param(key: str, args: Mapping[str, str]) -> Optional[str]:
    return args.get(key) or args.get(key.lower())


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
    * Any other urls are routed as {route}/{api_endpoint}/
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
        map_arg = get_ows_param('MAP', args)
        if map_arg:
            project = unquote_plus(_decode('MAP', map_arg))
        else:
            project = request.headers.get('X-Qgis-Project')

        # Ensure that project path start with a '/'
        if project and not project.startswith('/'):
            project = f"/{project}"

        if get_ows_param('SERVICE', args) is not None:
            # OWS project
            if not project:
                # Check project in the path
                project = request.path
                if route != '/':
                    project = project.removeprefix(route)
            elif route != request.path and route != request.path.removesuffix('/'):
                # Do not allow arbitrary path
                logger.error("Route '%s'  does not match request path %s", route, request.path)
                raise web.HTTPForbidden()

            logger.trace("DefaultRouter::router %s OWS request detected", request.url)
            return Route(route=route, project=project)
        else:
            # Get api path
            # expecting {route}/{api}/{api_path}
            head = request.path.removeprefix(route).removeprefix('/')

            api, _, api_path = head.partition('/')
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
