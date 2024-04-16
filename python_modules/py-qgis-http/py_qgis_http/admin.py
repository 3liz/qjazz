import os

from pathlib import Path

from aiohttp import web
from pydantic import ValidationError
from typing_extensions import List

from py_qgis_contrib.core import logger

from .channel import Channel, ChannelStatus
from .channels import Channels
from .config import (
    ENV_CONFIGFILE,
    BackendConfig,
    RemoteConfigError,
    confservice,
    load_include_config_files,
    read_config_toml,
)
from .models import ErrorResponse, JsonModel, JsonValueType, Link
from .webutils import CORSHandler, make_link, public_location

#
# Backend managment handler
#


class BackendItem(JsonModel):
    name: str
    address: str
    serving: bool
    status: ChannelStatus
    config: BackendConfig
    links: List[Link]


class BackendSummary(JsonModel):
    name: str
    address: str
    serving: bool
    status: ChannelStatus
    links: List[Link]


class BackendList(JsonModel):
    backends: List[BackendSummary]


def backend_summary(request: web.Request, channel: Channel) -> BackendSummary:
    return BackendSummary(
        name=channel.name,
        serving=channel.serving,
        address=channel.address,
        status=channel.status,
        links=[
            make_link(
                request,
                rel="backend",
                title="Qgis Backend",
                path=f"/backends/{channel.name}",
            ),
        ],
    )


def backends_list_route(
    channels: Channels,
    cors_options_handler: CORSHandler,
) -> web.RouteDef:

    class BackendListView(web.View):

        async def get(self) -> web.Response:
            """ Get backend
            """
            return web.Response(
                content_type="application/json",
                text=BackendList(
                    backends=[
                        backend_summary(self.request, chan) for chan in channels.backends
                    ],
                ).model_dump_json(),
            )

        async def options(self) -> web.Response:
            return await cors_options_handler(
                self.request,
                allow_methods="GET",
                allow_headers="Authorization",
            )

    return web.view('/backends', BackendListView)


def backends_route(
    channels: Channels,
    cors_options_handler: CORSHandler,
) -> web.RouteDef:

    class BackendView(web.View):

        async def get(self) -> web.Response:
            """ Get backend/Channel
            """
            name = self.request.match_info['Name']
            channel = channels.channel_by_name(name)
            if not channel:
                raise web.HTTPNotFound(reason=f"Backend '{name}' does not exists")
            return web.Response(
                content_type="application/json",
                text=BackendItem(
                    name=channel.name,
                    address=channel.address,
                    serving=channel.serving,
                    status=channel.status,
                    config=channel.config,
                    links=[
                        make_link(
                            self.request,
                            rel="self",
                            title="Backend description",
                            path=f"/backends/{name}",
                        ),
                    ],
                ).model_dump_json(),
            )

        async def post(self) -> web.Response:
            """ Add new backend
            """
            name = self.request.match_info['Name']
            if channels.get_backend(name):
                raise web.HTTPConflict(reason=f"Backend '{name}' already exists")
            try:
                backend = BackendConfig.model_validate_json(await self.request.text())
                await channels.add_backend(name, backend)

                return web.Response(
                    status=201,
                    headers={"Location": public_location(self.request)},
                )
            except ValidationError as err:
                raise web.HTTPBadRequest(reason=str(err))

        async def put(self) -> web.Response:
            """ Replace backend
            """
            name = self.request.match_info['Name']
            if not channels.get_backend(name):
                raise web.HTTPNotFound(reason=f"Backend '{name}' does not exists")
            try:
                backend = BackendConfig.model_validate_json(await self.request.text())
                channels.remove_backend(name)
                await channels.add_backend(name, backend)
                return web.Response()
            except ValidationError as err:
                raise web.HTTPBadRequest(reason=str(err))

        async def delete(self) -> web.Response:
            """ Remove backend
            """
            name = self.request.match_info['Name']
            if not channels.get_backend(name):
                raise web.HTTPNotFound(reason=f"Backend '{name}' does not exists")
            channels.remove_backend(name)
            return web.Response()

        async def head(self) -> web.Response:
            name = self.request.match_info['Name']
            if not channels.get_backend(name):
                raise web.HTTPNotFound(reason=f"Backend {name} does not exists")
            return web.Response(content_type="application/json")

        async def options(self) -> web.Response:
            return await cors_options_handler(
                self.request,
                allow_methods="GET, POST, PUT, HEAD, DELETE, OPTIONS",
                allow_headers="Authorization",
            )

    return web.view('/backends/{Name}', BackendView)

#
# Config managment handler
#


def config_route(
    channels: Channels,
    cors_options_handler: CORSHandler,
) -> web.RouteDef:

    class ConfigView(web.View):
        """ Configuration Handler
        """
        async def get(self) -> web.Response:
            """ Return actual configuration
            """
            response = web.Response(
                status=200,
                content_type="application/json",
                text=confservice.conf.model_dump_json(),
            )
            response.last_modified = confservice.last_modified
            return response

        async def patch(self):
            """ Patch configuration with request content
            """
            try:
                obj = JsonValueType.validate_json(await self.request.text())
                confservice.update_config(obj)

                level = logger.set_log_level()
                logger.info("Log level set to %s", level.name)

                # Resync channels
                await channels.init_channels()
            except ValidationError as err:
                return web.Response(
                    status=400,
                    content_type="application/json",
                    text=ErrorResponse(
                        message="Invalid json body",
                        details=err.json(include_url=False),
                    ).model_dump_json(),
                )

        async def put(self):
            """ Reload configuration
            """
            # If remote url is defined, load configuration
            # from it
            config_url = confservice.conf.config_url
            try:
                if config_url.is_set():
                    await config_url.load_configuration()
                elif ENV_CONFIGFILE in os.environ:
                    # Fallback to configfile (if any)
                    configpath = Path(os.environ[ENV_CONFIGFILE])
                    logger.info("** Reloading config from %s **", configpath)
                    obj = read_config_toml(
                        configpath,
                        location=str(configpath.parent.absolute()),
                    )
                else:
                    obj = {}

                confservice.update_config(obj)
                if confservice.conf.includes:
                    load_include_config_files(confservice.conf)
                # Update log level
                level = logger.set_log_level()
                logger.info("Log level set to %s", level.name)

                # Resync channels
                await channels.init_channels()
            except RemoteConfigError as err:
                raise web.HTTPBadGateway(reason=str(err))
            except ValidationError as err:
                raise web.HTTPBadRequest(reason=str(err))

        async def options(self) -> web.Response:
            return await cors_options_handler(
                self.request,
                allow_methods="GET, PATCH, PUT, OPTIONS",
                allow_headers="Authorization",
            )

    return web.view('/config', ConfigView)
