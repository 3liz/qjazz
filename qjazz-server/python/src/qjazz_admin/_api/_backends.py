# import traceback
from aiohttp import web
from pydantic import TypeAdapter, ValidationError

from ..models import (
    BackendStatus,
    PoolBackendsResponse,
    PoolInfos,
    PoolListResponse,
)
from .utils import _http_error, _link


class _Backends:
    async def get_pools(self, request):
        """
        summary: Return the list of managed pools
        description: >
            Return description of all of managed pools
        tags:
          - pools
        responses:
            "200":
                description: >
                    Returns the list of all registered pools
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolListResponse'
        """
        body = [
            PoolInfos._from_pool(
                pool,
                [
                    _link(
                        request,
                        "item",
                        f"/pools/{pool.label}",
                        title=pool.title,
                        description=pool.description,
                    ),
                ],
            )
            for pool in self.service.pools
        ]
        return web.Response(
            content_type="application/json",
            text=PoolListResponse.dump_json(body, by_alias=True, exclude_none=True).decode(),
        )

    async def patch_pools(self, request):
        """
        summary: Resynchronize all pools
        description: |
            Resynchronize all pools with their backends.

            This is necessary when rescaling backends services
            or adding new monitored pools.
        tags:
          - pools
        responses:
            "200":
                description: >
                    Returns the list of all registered pools
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolListResponse'
        """
        await self.service.synchronize()

        body = [
            PoolInfos._from_pool(
                pool,
                [_link(request, "item", f"/pools/{pool.label}")],
            )
            for pool in self.service.pools
        ]
        return web.Response(
            content_type="application/json",
            text=PoolListResponse.dump_json(body, by_alias=True, exclude_none=True).decode(),
        )

    async def get_pool_infos(self, request):
        """
        summary: "Pool infos"
        description: >
            Return pool infos and related links
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools
        responses:
            "200":
                description: >
                    Returns pool infos and related links
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolInfos'
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        return web.Response(
            content_type="application/json",
            text=PoolInfos._from_pool(
                pool,
                links=[
                    _link(request, "self", f"/pools/{pool.label}", title="Pool info"),
                    _link(
                        request,
                        "backends",
                        f"/pools/{pool.label}/backends",
                        title="Backends list",
                    ),
                    _link(
                        request,
                        "config",
                        f"/pools/{pool.label}/config",
                        title="Backend configuration",
                    ),
                    _link(
                        request,
                        "catalog",
                        f"/pools/{pool.label}/catalog",
                        title="Backend's projects catalog",
                    ),
                    _link(
                        request,
                        "cache",
                        f"/pools/{pool.label}/cache",
                        title="Backend's projects cache",
                    ),
                ],
            ).model_dump_json(),
        )

    async def get_pool_backends(self, request):
        """
        summary: "Backends status"
        description: >
            Return backend's pool status as
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools
        responses:
            "200":
                description: >
                    Returns all backend's status for that pool
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolBackendsResponse'
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        stats = await pool.stats()
        return web.Response(
            content_type="application/json",
            text=PoolBackendsResponse(
                label=pool.label,
                address=pool.address,
                backends=[BackendStatus.model_validate(s) for _, s in stats],
            ).model_dump_json(),
        )

    async def get_pool_test(self, request):
        """
        summary: "Backend test"
        description: >
            Send a test request
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
          - in: query
            schema:
                type: int
            required: true
            description: Delay in seconds to apply to backend response
        tags:
          - pools
        responses:
            "200":
                description: Test passed
                content:
                    text/plain:
                        schema:
                            type: string
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        pool = self._pool(request)
        try:
            delay = TypeAdapter(int).validate_json(request.query["delay"])
        except KeyError:
            _http_error(web.HTTPBadRequest, message="Missing 'delay' parameter")
        except ValidationError:
            _http_error(web.HTTPBadRequest, message="Invalid 'delay' parameter")

        await pool.test_backend(delay)
        return web.Response(content_type="text/plain", text="Test passed")
