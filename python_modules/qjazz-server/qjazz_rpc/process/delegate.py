"""
    Api Delegation

    Define a 'catch all' api used for delegating request execution
    with a custom rootpath.

    Atm, the qgis server api does not enable to specify a custom rootpath,
    this is problematic when running behind a proxy since there is no way
    to specify a custom URL as for ows api (i.e `X-Qgis-Service-Url` header)

    Also there is no way to iterate over registered api and check for
    `accept` method, we only may rely on the api name to fetch the api

    NOTE: template handling is broken in Qgis server: instead of trying
    to get resource path for api root name it try to resolve the path from
    the url and this does not work in delegated api url.
"""
import traceback

from typing_extensions import List

from qgis.PyQt.QtCore import QUrl
from qgis.server import QgsServerApi, QgsServerApiContext

from qjazz_contrib.core import logger

ROOT_DELEGATE = '/__delegate__'

API_ALIASES = {
    'WFS3': 'OGC WFS3 (Draft)',
}


class ApiDelegate(QgsServerApi):

    __instances: List[QgsServerApi] = []  #  noqa RUF012

    def __init__(
            self,
            serverIface,
    ):
        super().__init__(serverIface)
        self.__instances.append(self)
        self._rootpath = None
        self._extra_path = ""

    def name(self) -> str:
        return "API Delegate"

    def rootPath(self) -> str:
        return self._rootpath or '/'

    def accept(self, url: QUrl) -> bool:
        """ Override the api to actually match the rootpath
        """
        path = url.path()
        try:
            index = path.index(ROOT_DELEGATE)
        except ValueError:
            return False

        self._rootpath = path[:index]
        self._extra_path = path[index + len(ROOT_DELEGATE):]
        return True

    def executeRequest(self, context):
        request = context.request()
        api = request.header("x-qgis-api")
        api = API_ALIASES.get(api.upper(), api)
        logger.debug("Executing delegated api for %s (root: %s)", api, self._rootpath)
        if api:
            api = self.serverIface().serviceRegistry().getApi(api)
        if not api:
            response = context.response()
            response.clear()
            response.setStatusCode(404)
        else:
            # Substitute path
            url = request.url()
            url.setPath(f"{self._rootpath}{self._extra_path}")
            request.setUrl(url)
            # Delegate to api
            try:
                api.executeRequest(
                    QgsServerApiContext(
                        self._rootpath,
                        context.request(),
                        context.response(),
                        context.project(),
                        context.serverInterface(),
                    ),
                )
            except Exception:
                logger.critical(traceback.format_exc())
                response = context.response()
                response.clear()
                response.setStatusCode(500)
