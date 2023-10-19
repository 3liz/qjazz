# import traceback
from aiohttp import web

from .models import (
    ErrorResponse,
)

from .pool import PoolClient

from ._api.utils import (
    API_VERSION,
    BaseHandlers,
)

from ._api import (
    _Backends,
    _Config,
    _Cache,
    _Projects,
    _Plugins,
)


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
            web.get(f'/{API_VERSION}/pools', self.get_pools, allow_head=False),
            web.get(f'/{API_VERSION}/pools/{{Id}}', self.get_pool_infos, allow_head=False),
            web.get(f'/{API_VERSION}/pools/{{Id}}/backends', self.get_pool_backends, allow_head=False),
            # Config
            web.get(f'/{API_VERSION}/pools/{{Id}}/config', self.get_pool_config, allow_head=False),
            web.put(f'/{API_VERSION}/pools/{{Id}}/config', self.put_pool_config),
            # Cache
            web.get(f'/{API_VERSION}/pools/{{Id}}/catalog', self.get_catalog, allow_head=False),
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache', self.get_cache, allow_head=False),
            web.post(f'/{API_VERSION}/pools/{{Id}}/cache', self.post_cache),
            web.put(f'/{API_VERSION}/pools/{{Id}}/cache', self.put_cache),
            web.delete(f'/{API_VERSION}/pools/{{Id}}/cache', self.delete_cache),
            # Project
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache/project', self.get_project, allow_head=False),
            web.delete(f'/{API_VERSION}/pools/{{Id}}/cache/project', self.delete_project),
            web.get(f'/{API_VERSION}/pools/{{Id}}/cache/project/info', self.get_project_info, allow_head=False),
            # Plugins
            web.get(f'/{API_VERSION}/pools/{{Id}}/plugins', self.get_plugins, allow_head=False),
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
