# import traceback
from aiohttp import web

from .. import swagger

from pydantic import (
    BaseModel,
)

from typing_extensions import (
    List,
    Dict,
)

from ..models import (
    CacheItemPool,
)

from ..errors import (
    ServiceNotAvailable,
)

from .utils import (
    _http_error,
)


@swagger.model
class LayerInfos(BaseModel):
    layerId: str
    name: str
    source: str
    crs: str
    isValid: bool
    isSpatial: bool


@swagger.model
class ProjectInfo(BaseModel):
    status: str
    uri: str
    filename: str
    crs: str
    lastModified: str
    storage: str
    hasBadLayers: bool
    layers: List[LayerInfos]
    cacheId: str
    serverAddress: str


def cache_item_pool_response(response: Dict[str, Dict], links: List[swagger.Link] = []) -> str:
    return CacheItemPool.validate({'pool': response, 'links': links}).model_dump_json()


class _Projects:

    #
    # Projects
    #

    async def get_project(self, request):
        """
        summary: "Get project's status cache"
        description: >
            Returns the project's cache status
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
          - in: query
            name: uri
            schema:
                type: str
            description: The project uri
        tags:
          - backends.cache.project
        responses:
            "200":
                description: >
                    Returns project's status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CacheItemPool'
            "400":
                description: >
                    Missing uri in query string
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "502":
                description: >
                    Backends are unavailables
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        try:
            uri = request.query['uri']
        except KeyError:
            _http_error(web.HTTPBadRequest, message="Missing project's uri")
        try:
            response = await pool.checkout_project(uri)
            return web.Response(
                content_type="application/json",
                text=cache_item_pool_response(response),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def delete_project(self, request):
        """
        summary: "Remove project from cache"
        description: >
            Returns the project's cache status
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
          - in: query
            name: uri
            schema:
                type: str
            description: The project uri
        tags:
          - backends.cache.project
        responses:
            "200":
                description: >
                    Returns project's status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CacheItemPool'
            "400":
                description: >
                    Missing uri in query string
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "502":
                description: >
                    Backends are unavailables
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        try:
            uri = request.query['uri']
        except KeyError:
            _http_error(web.HTTPBadRequest, message="Missing project's uri")
        try:
            response = await pool.drop_project(uri)
            return web.Response(
                content_type="application/json",
                text=cache_item_pool_response(response),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def get_project_info(self, request):
        """
        summary: "Get project's infos"
        description: >
            Returns detailed informations about the project,
            Note that the project must be in cache
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
          - in: query
            name: uri
            schema:
                type: str
            description: The project uri
        tags:
          - backends.cache.project
        responses:
            "200":
                description: >
                    Returns project's status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ProjectInfo'
            "400":
                description: >
                    Missing uri in query string
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "502":
                description: >
                    Backends are unavailables
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        try:
            uri = request.query['uri']
        except KeyError:
            _http_error(web.HTTPBadRequest, message="Missing project's uri")
        try:
            response = await pool.project_info(uri)
            if not response:
                _http_error(web.HTTPNotFound, f"Project {uri} not in cache")
            return web.Response(
                content_type="application/json",
                text=ProjectInfo.model_validate(response).model_dump_json()
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )
