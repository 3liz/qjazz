import traceback
import asyncio

from aiohttp import web, WSMsgType
from pydantic import BaseModel

from typing_extensions import (
    Dict,
)

from py_qgis_contrib.core.config import (
    confservice,
)

from py_qgis_contrib.core import logger

from .models import (
    ErrorResponse,
)

from .pool import PoolClient

from ._api.utils import (
    API_VERSION,
    BaseHandlers,
    _http_error,
)

from ._api import (
    _Backends,
    _Config,
    _Cache,
    _Projects,
    _Plugins,
)


from . import swagger


@swagger.model
class WatchResponse(BaseModel):
    label: str
    address: str
    backend_status: Dict[str, bool]


class Handlers(
    BaseHandlers,
    _Backends,
    _Config,
    _Cache,
    _Projects,
    _Plugins,
):

    @property
    def routes(self):
        return [
            # backends
            web.get(f'/{API_VERSION}/pools', self.get_pools, allow_head=False),
            web.patch(f'/{API_VERSION}/pools', self.patch_pools),
            web.get(f'/{API_VERSION}/pools/{{Id}}', self.get_pool_infos, allow_head=False),
            web.get(f'/{API_VERSION}/pools/{{Id}}/backends', self.get_pool_backends, allow_head=False),
            # Config
            web.get(f'/{API_VERSION}/pools/{{Id}}/config', self.get_pool_config, allow_head=False),
            web.put(f'/{API_VERSION}/pools/{{Id}}/config', self.put_pool_config),
            # Cache
            web.get(f'/{API_VERSION}/pools/{{Id}}/catalog', self.get_catalog, allow_head=False),
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache', self.get_cache, allow_head=False),
            web.patch(f'/{API_VERSION}/pools/{{Id}}/cache', self.patch_cache),
            web.put(f'/{API_VERSION}/pools/{{Id}}/cache', self.put_cache),
            web.delete(f'/{API_VERSION}/pools/{{Id}}/cache', self.delete_cache),
            # Project
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache/project', self.get_project, allow_head=False),
            web.delete(f'/{API_VERSION}/pools/{{Id}}/cache/project', self.delete_project),
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache/project/info', self.get_project_info, allow_head=False),
            # Plugins
            web.get(f'/{API_VERSION}/pools/{{Id}}/plugins', self.get_plugins, allow_head=False),

            # Config
            web.patch(f'/{API_VERSION}/config', self.patch_config),

            # Watch
            web.get(f'/{API_VERSION}/watch', self.ws_watch),
        ]

    def _pool(self, request) -> PoolClient:
        Id = request.match_info['Id']
        try:
            return self.service[Id]
        except KeyError:
            raise web.HTTPNotFound(
                content_type="application/json",
                text=ErrorResponse(message=f"Unknown pool '{Id}'").model_dump_json(),
            )

    async def patch_config(self, request):
        """
        summary: Reload config
        description: |
            Reload config from external URL
        tags:
          - config
        responses:
            "200":
                description: >
                    The new configuration fragment has been retrieved and
                    the actual configuration has been updated
                    Returns the actual configuration
                content:
                    application/json:
                        schema:
                            type: object
            "403":
                description: >
                    No configuration url is defined
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        cnf = confservice.conf.config_url
        if await cnf.load_configuration():

            # Update log level
            level = logger.set_log_level()
            logger.info("Log level set to %s", level.name)

            # Update service
            await self.service.synchronize()

            return web.Response(
                content_type="application/json",
                text=confservice.conf.model_dump_json(),
            )
        else:
            _http_error(
                web.HTTPUnauthorized,
                "No config url defined",
            )

    async def ws_watch(self, request):
        """
        summary: Watch (websocket)
        description: |
            Open a websocket for monitoring backends
            status
        tags:
          - healthcheck
        responses:
            "200":
                description: >
                    Send backend's status changes over the web
                    socket.
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/WatchResponse'

        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async def watch():
            try:
                async for pool, statuses in self.service.watch():
                    if ws.closed:
                        break
                    await ws.send_str(
                        WatchResponse(
                            label=pool.label,
                            address=pool.address,
                            backend_status=dict(statuses),
                        ).model_dump_json()
                    )
            except Exception:
                logger.critical(traceback.format_exc())

        watch_task = asyncio.create_task(watch())
        try:
            async for msg in ws:
                match msg.type:
                    case WSMsgType.TEXT:
                        match msg.data:
                            case 'close':
                                ws.close()
                    case WSMsgType.ERROR:
                        logger.error("WS connection error %s", ws.exception())
        finally:
            if watch_task:
                watch_task.cancel()
            logger.info("WS connection closed")
