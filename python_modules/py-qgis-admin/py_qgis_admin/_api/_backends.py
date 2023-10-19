# import traceback
from aiohttp import web

from ..models import (
    BackendStatus,
    PoolBackendsResponse,
    PoolInfos,
    PoolListResponse,
)

from .utils import (
    _link,
)


class _Backends:

    async def get_pools(self, request):
        """
        description: Return the list of managed pools
        tags:
          - backends
        responses:
            "200":
                description: >
                    Returns the list of all registered pools
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolListResponse'
        """
        body = [PoolInfos._from_pool(
            pool,
            [_link(request, "item", f"/pools/{pool.label}")],
        ) for pool in self.service.pools]
        return web.Response(
            content_type="application/json",
            text=PoolListResponse.dump_json(body, by_alias=True).decode(),
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
          - backends
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
                    _link(request, "self", f"/pools/{pool.label}"),
                    _link(request, "backends", f"/pools/{pool.label}/backends"),
                    _link(request, "config", f"/pools/{pool.label}/config"),
                ],
            ).model_dump_json(by_alias=True),
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
          - backends
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
