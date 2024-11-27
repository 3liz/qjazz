# import traceback
from aiohttp import web
from pydantic import (
    BaseModel,
    Json,
    JsonValue,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
)
from typing_extensions import Annotated, Dict, List

from .. import swagger
from ..errors import ServiceNotAvailable
from ..models import CacheItemPool, StringList
from .utils import _http_error, _link


@swagger.model
class CatalogItem(BaseModel):
    lastModified: Annotated[
        str,
        WithJsonSchema({
            "type": "string",
            "format": "date-time",
        }),
    ]
    name: str
    publicUri: str
    storage: str
    uri: str


CatalogResponse = swagger.model(
    TypeAdapter(List[CatalogItem]),
    name="CatalogResponse",
)


CacheContentResponse: TypeAdapter[Dict[str, CacheItemPool]] = swagger.model(
    TypeAdapter(Dict[str, CacheItemPool]),
    name="CacheContentResponse",
)


def cache_content_response(
    request: web.Request,
    label: str, response: Dict[str, JsonValue],
) -> Json:
    return CacheContentResponse.dump_json(
        CacheContentResponse.validate_python({
            uri: {
                "pool": item,
                "links": [
                    _link(
                        request,
                        rel="related",
                        path=f"/pools/{label}/cache/project?uri={uri}",
                        title="Project status",
                    ),
                    _link(
                        request,
                        rel="related",
                        path=f"/pools/{label}/cache/project/info?uri={uri}",
                        title="Project details",
                    ),
                ],
            }
            for uri, item in response.items()
        }),
        by_alias=True,
    ).decode()


class _Cache:

    #
    #  Cache methods
    #

    async def get_catalog(self, request):
        """
        summary: "Get backend's projects catalog"
        description: >
            Returns the list of all projects avaialables to the backend
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.cache
        responses:
            "200":
                description: >
                    Returns the list of availables projects
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CatalogResponse'
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

        resp = web.StreamResponse(
            status=200,
            reason='OK',
            headers={'Content-Type': 'application/json'},
        )

        await resp.prepare(request)
        await resp.write(b'[')
        count = 0
        length = 0
        try:
            async for item in pool.catalog():
                if count > 0:
                    await resp.write(b',')
                payload = CatalogItem.model_validate(item).model_dump_json().encode()
                await resp.write(payload)
                count += 1
                length += len(payload)
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

        length += 2 + (count - 1)
        resp.content_length = length

        await resp.write(b']')
        await resp.write_eof()

        return resp

    async def get_cache(self, request):
        """
        summary: "Get backend's cache content"
        description: >
            Returns a consolidated view of the backend's cache content
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.cache
        responses:
            "200":
                description: >
                    Returns the content of the cache
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CacheContentResponse'
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
            response = await pool.cache_content()
            return web.Response(
                content_type="application/json",
                text=cache_content_response(
                    request,
                    pool.label,
                    response,
                ),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def patch_cache(self, request):
        """
        summary: "Synchronize cache"
        description: >
            Synchronize and update cache between all backends
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.cache
        responses:
            "200":
                description: >
                    Returns the content of the cache
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CacheContentResponse'
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
            response = await pool.synchronize_cache()
            return web.Response(
                content_type="application/json",
                text=cache_content_response(
                    request,
                    pool.label,
                    response,
                ),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def put_cache(self, request):
        """
        summary: "Pull/Update projects in cache for backend"
        description: >
            Update requested projects for backend's cache
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.cache
        requestBody:
            desccription: The list of projects to pull/update
            required: true
            content:
                application/json:
                    schema:
                        $ref: '#/definitions/StringList'
        responses:
            "200":
                description: >
                    Returns the content of the cache
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/CacheContentResponse'
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
            projects = StringList.validate_json(await request.text())
            response = await pool.pull_projects(*projects)
            return web.Response(
                content_type="application/json",
                text=cache_content_response(
                    request,
                    pool.label,
                    response,
                ),
            )
        except ValidationError as e:
            _http_error(
                web.HTTPBadRequest,
                message="Invalid json body",
                details=e.json(include_url=False),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def delete_cache(self, request):
        """
        summary: "Clear cache"
        description: >
            Clear cache for backends
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.cache
        responses:
            "200":
                description: >
                    Cache is cleared for all backends
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
            await pool.clear_cache()
            return web.json_response({})
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )
