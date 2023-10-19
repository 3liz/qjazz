# import traceback
from aiohttp import web

from pydantic import (
    ValidationError,
)

from ..models import (
    PoolBackendConfig,
    PoolSetConfigResponse,
    JsonValidator,
)

from ..errors import (
    ServiceNotAvailable,
    RequestArgumentError,
)

from .utils import (
    _http_error,
)


class _Config:

    async def get_pool_config(self, request):
        """
        summary: "Pool backends configuration"
        description: >
            Returns pool backends configuration
        parameters:
          - in: path
            name: Id
            schema:
              type: string
            required: true
            description: Identifier for the backend
        tags:
        - backends.config
        responses:
            "200":
                description: >
                    Returns the backends configuration as json object
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PoolBackendConfig'
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
            conf, env = await pool.get_config(include_env=True)
            return web.Response(
                content_type="application/json",
                text=PoolBackendConfig(
                    label=pool.label,
                    address=pool.address,
                    config=conf,
                    env=env,
                ).model_dump_json(),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )

    async def put_pool_config(self, request):
        """
        summary: "Set pool backends configuration"
        description: >
            Set pool backends configuration and returns
            the configuration difference
        parameters:
          - in: path
            name: Id
            schema:
              type: string
            required: true
            description: Identifier for the backend
        tags:
        - backends.config
        responses:
            "200":
                description: >
                    The configuration has been applied with success and
                    the configuration diff  is returned as json object
                content:
                    application/json:
                        schema:
                            type: object
            "404":
                description: >
                    The requested backends does not exists
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
            "400":
                description: >
                    Invalid configuration input
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
            req = JsonValidator(body=await request.text())
            return web.Response(
                content_type="application/json",
                text=PoolSetConfigResponse(
                    label=pool.label,
                    address=pool.address,
                    diff=await pool.set_config(req.body, diff=True)
                ).model_dump_json(),
            )
        except ValidationError as e:
            _http_error(
                web.HTTPBadRequest,
                message="Invalid json body",
                details=e.json(include_url=False),
            )
        except RequestArgumentError as e:
            _http_error(web.HTTPBadRequest, message=e.details)
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )
