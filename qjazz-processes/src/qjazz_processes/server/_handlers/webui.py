from aiohttp import web

from .protos import HandlerProto


class WebUI(HandlerProto):
    async def ui_dashboard(self, request: web.Request) -> web.StreamResponse:
        index = request.match_info.get("Path") or "dashboard.html"
        return web.FileResponse(
            path=self._staticpath.joinpath(index),
        )

    async def ui_jobdetails(self, request: web.Request) -> web.StreamResponse:
        index = request.match_info.get("Path") or "details.html"
        return web.FileResponse(path=self._staticpath.joinpath(index))
