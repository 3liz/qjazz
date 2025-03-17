# import traceback
from pathlib import Path
from typing import List

from aiohttp import web
from pydantic import BaseModel, Json, TypeAdapter

from .. import swagger
from ..errors import ServiceNotAvailable
from .utils import _http_error


@swagger.model
class PluginInfo(BaseModel):
    name: str
    path: Path
    pluginType: str
    metadata: Json


PluginListResponse = swagger.model(
    TypeAdapter(List[PluginInfo]),
    name="PluginListResponse",
)


class _Plugins:
    async def get_plugins(self, request):
        """
        summary: "Get backend's plugins"
        description: >
            Returns loaded plugins information in backends
        parameters:
          - in: path
            name: Id
            schema:
                type: string
            required: true
            description: Identifier for the backend
        tags:
          - pools.plugins
        responses:
            "200":
                description: >
                    Returns the plugin's informations
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/PluginListResponse'
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
            response = await pool.list_plugins()
            return web.Response(
                content_type="application/json",
                text=PluginListResponse.dump_json(
                    PluginListResponse.validate_python(response),
                ).decode(),
            )
        except ServiceNotAvailable:
            _http_error(
                web.HTTPBadGateway,
                f"No backends availables for pool '{pool.label}'",
            )
