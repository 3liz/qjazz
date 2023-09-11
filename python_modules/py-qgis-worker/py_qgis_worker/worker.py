import multiprocessing as mp
import asyncio

from typing_extensions import (
    AsyncIterator,
    Optional,
    Dict,
    Tuple,
    Any,
)

from .config import WorkerConfig
from . import _op_worker
from . import messages as _m

from py_qgis_contrib.core.config import ConfigProxy
from py_qgis_contrib.core import logger

from functools import cached_property


class WorkerError(Exception):
    def __init__(self, code: int, details: Any = None):
        self.code = code
        self.details = details


class Worker(mp.Process):

    def __init__(self, config: WorkerConfig):
        super().__init__(name=config.name, daemon=True)
        self._worker_conf = config
        self._parent_conn, self._child_conn = mp.Pipe(duplex=True)
        self._event = mp.Event()
        self._timeout = config.worker_timeout

    @property
    def config(self) -> WorkerConfig:
        return self._worker_conf

    def task_done(self) -> bool:
        """ Return true if there is no processing
            at hand
        """
        not self._event.is_set()

    async def wait_until_task_done(self):
        """ Consume all remaining data that may be send
            by the worker task.
            This is required if a client abort the request
            in the middle.
        """
        logger.debug("Waiting until task done")
        while self._event.is_set():
            try:
                _ = await self.io.read_bytes(1)
            except asyncio.TimeoutError:
                pass
        self.io.flush()

    def dump_config(self) -> Dict:
        if isinstance(self._worker_conf, ConfigProxy):
            return self._worker_conf.service.conf.model_dump()
        else:
            return self._worker_conf.model_dump()

    async def update_config(self, obj: Dict):
        if isinstance(self._worker_conf, ConfigProxy):
            self._worker_conf.service.update_config(obj)
            status, resp = await self.io.send_message(
                _m.PutConfig(config=obj),
                timeout=self._timeout,
            )
            # Update timeout config
            self._timeout = self.config.worker_timeout
            # Update log level
            level = logger.set_log_level()
            logger.info("Log level set to %s", level.name)
            logger.trace("Updated worker with configuration\n %s", obj)
        else:
            raise WorkerError(403, "Cannot update local configuration")

    def run(self):
        """ Override """
        server = _op_worker.setup_server(self._worker_conf)
        _op_worker.qgis_server_run(
            server,
            self._child_conn,
            self._worker_conf,
            self._event,
        )

    @cached_property
    def io(self) -> _m.Pipe:
        return _m.Pipe(self._parent_conn)

    # API stubs

    async def ping(self, echo: str) -> str:
        """  Send ping with echo string
        """
        status, resp = await self.io.send_message(
            _m.Ping(echo),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)
        return resp

    #
    # Requests
    #

    async def ows_request(
        self,
        service: str,
        request: str,
        target: str,
        url: str = "",
        version: Optional[str] = None,
        direct: bool = False,
        options: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        request_id: str = "",
        debug_report: bool = False,
    ) -> Tuple[_m.RequestReply, Optional[AsyncIterator]]:
        """ Send OWS request

            Exemple:
            ```
            resp, stream = await worker.ows_request(
                service="WFS",
                request="GetCapabilities",
                target="/france/france_parts",
                url="http://localhost:8080/test.3liz.com",
            )
            if resp.status_code != 200:
                print("Request failed")
            data = resp.data
            if stream:
                # Stream remaining bytes
                async for chunk in stream:
                    # Do something with chunk of data
                    ...
            ```
        """
        status, resp = await self.io.send_message(
            _m.OWSRequest(
                service=service,
                request=request,
                version=version,
                options=options,
                target=target,
                url=url,
                direct=direct,
                headers=headers or {},
                request_id=request_id,
                debug_report=debug_report,
            ),
            timeout=self._timeout,
        )

        # Request failed before reaching Qgis server
        if status != 200:
            raise WorkerError(status, resp)

        if resp.chunked:
            return resp, self.io.read_bytes()
        else:
            return resp, None

    async def request(
        self,
        url: str,
        data: bytes,
        target: Optional[str],
        direct: bool = False,
        method: _m.HTTPMethod = _m.HTTPMethod.GET,
        headers: Dict[str, str] = None,
        request_id: str = "",
        debug_report: bool = False,
    ) -> Tuple[_m.RequestReply, Optional[AsyncIterator[bytes]]]:
        """ Send generic (api) request

            Exemple:
            ```
            resp, stream = await worker.request(
                url="/wfs3/collections",
                target="/france/france_parts",
            )
            if resp.status_code != 200:
                print("Request failed")
            data = resp.data
            # Stream remaining bytes
            if stream:
                async for chunk in stream:
                    # Do something with chunk of data
                    ...
            ```
        """
        status, resp = await self.io.send_message(
            _m.Request(
                url=url,
                method=method,
                data=data,
                target=target,
                direct=direct,
                headers=headers,
                request_id=request_id,
            ),
            timeout=self._timeout,
        )
        # Request failed before reaching Qgis server
        if status != 200:
            raise WorkerError(status, resp)

        if resp.chunked:
            return resp, self.io.read_bytes(timeout=self._timeout)
        else:
            return resp, None

    #
    # Cache
    #

    async def checkout_project(self, uri: str, pull: bool = False) -> _m.CacheInfo:
        """ Checkout project status

            If pull is True, the cache will be updated
            according the checkout status:

            * `NEW`: The Project exists and will be loaded in cache
            * `NEEDUPDATE`: The Project is already loaded and will be updated in cache
            * `UNCHANGED`: The Project is loaded, up to date. Nothing happend
            * `REMOVED`: The Project is loaded but has been removed from storage;
              project will be removed from cache.
            * `NOTFOUND`: The project does not exists, nor in storage, nor in cache.
        """
        status, resp = await self.io.send_message(
            _m.CheckoutProject(uri=uri, pull=pull),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)
        return resp

    async def drop_project(self, uri: str) -> _m.CacheInfo:
        """ Drop project from cache
        """
        status, resp = await self.io.send_message(
            _m.DropProject(uri=uri),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)
        return resp

    async def list_cache(
        self,
        status_filter: Optional[_m.CheckoutStatus] = None,
    ) -> Tuple[int, AsyncIterator[_m.CacheInfo]]:
        """ List projects in cache

            Return 2-tuple where first element is the number
            of items in cache and the second elemeent an async
            iterator yielding CacheInfo items
        """
        status, resp = await self.io.send_message(
            _m.ListCache(status_filter),
            timeout=self._timeout,
        )

        if status != 200:
            raise WorkerError(status, resp)

        if resp > 0:
            async def _stream():
                status, resp = await self.io.read_message(timeout=self._timeout)
                while status == 206:
                    yield resp
                    status, resp = await self.io.read_message(timeout=self._timeout)
            # Incomplete transmission ?
            if status != 200:
                raise WorkerError(status, resp)

            return resp, _stream()
        else:
            return resp, None

    async def clear_cache(self) -> None:
        """  Clear all items in cache
        """
        status, resp = await self.io.send_message(
            _m.ClearCache(),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)

    async def catalog(self, location: str = None) -> AsyncIterator[_m.CatalogItem]:
        """ Return all projects availables

            If location is set, returns only projects availables for
            this particular location
        """
        status, resp = await self.io.send_message(
            _m.Catalog(location=location),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)

        async def _stream():
            status, item = await self.io.read_message(timeout=self._timeout)
            while status == 206:
                yield item
                status, item = await self.io.read_message(timeout=self._timeout)
            # Incomplete transmission ?
            if status != 200:
                raise WorkerError(status, item)

        return _stream()

    async def project_info(self, uri: str) -> _m.ProjectInfo:
        """ Return project information from loaded project in
            cache

            The method will NOT load the project in cache
        """
        status, resp = await self.io.send_message(
            _m.GetProjectInfo(uri=uri),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)

        return resp
    #
    # Plugins
    #

    async def list_plugins(self) -> Tuple[int, Optional[AsyncIterator[_m.PluginInfo]]]:
        """ List projects in cache

            Return 2-tuple where first element is the number
            of loaded plugins and the second elemeent an async
            iterator yielding PluginInfo items
        """
        status, resp = await self.io.send_message(
            _m.Plugins(),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)
        if resp > 0:
            async def _stream():
                status, resp = await self.io.read_message(timeout=self._timeout)
                while status == 206:
                    yield resp
                    status, resp = await self.io.read_message(timeout=self._timeout)
                # Incomplete transmission ?
                if status != 200:
                    raise WorkerError(status, resp)
            return resp, _stream()
        else:
            return resp, None
