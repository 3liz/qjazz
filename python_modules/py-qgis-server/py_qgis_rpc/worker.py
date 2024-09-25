import asyncio
import multiprocessing as mp

from functools import cached_property

from typing_extensions import AsyncIterator, Dict, Optional, Tuple, cast

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigProxy

from . import _op_worker
from . import messages as _m
from .config import WORKER_SECTION, WorkerConfig, confservice


class WorkerError(Exception):
    def __init__(self, code: int, details: str = ""):
        self.code = code
        self.details = details


class Worker(mp.Process):
    """ Worker stub api

        *WARNING*: There is a race condition between
        tasks: use a lock mecanism to protect
        concurrent calls.
    """

    def __init__(self, config: WorkerConfig, name: Optional[str] = None):
        super().__init__(name=name or config.name, daemon=True)
        self._worker_conf = config
        self._parent_conn, self._child_conn = mp.Pipe(duplex=True)
        self._done_event = mp.Event()
        self._timeout = config.process_timeout
        self._loglevel = logger.log_level()

    @property
    def config(self) -> WorkerConfig:
        return self._worker_conf

    def task_done(self) -> bool:
        """ Return true if there is no processing
            at hand
        """
        return self._done_event.is_set()

    async def quit(self):
        """ Send a quit message
        """
        status, _ = await self.io.send_message(_m.Quit(), timeout=self._timeout)
        if status != 200:
            raise WorkerError(status, "Message failure (QUIT)")

    async def consume_until_task_done(self):
        """ Consume all remaining data that may be send
            by the worker task.
            This is required if a client abort the request
            in the middle.
        """
        logger.debug("Waiting until task done")
        while not self._done_event.is_set():
            try:
                _ = await self.io.read_bytes(1)
            except asyncio.TimeoutError:
                pass
        self.io.flush()

    async def update_config(self, worker_conf: WorkerConfig):
        self._worker_conf = worker_conf
        status, resp = await self.io.send_message(
            _m.PutConfig(
                config={
                    'logging': {'level': logger.log_level()},
                    'worker': worker_conf.model_dump(),
                },
            ),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)
        # Update timeout config
        self._timeout = self.config.process_timeout
        logger.trace(f"Updated config for worker '{self.name}'")

    def run(self) -> None:
        """ Override """
        logger.setup_log_handler(self._loglevel)

        confservice.validate({WORKER_SECTION: self._worker_conf})

        # Create proxy for allow update
        self._worker_conf = cast(WorkerConfig, ConfigProxy(confservice, WORKER_SECTION))
        server = _op_worker.setup_server(self._worker_conf)
        _op_worker.qgis_server_run(
            server,
            self._child_conn,
            self._worker_conf,
            self._done_event,
            name=self.name,
        )

    @cached_property
    def io(self) -> _m.Pipe:
        return _m.Pipe(self._parent_conn)

    # ================
    # API stubs
    # ================

    #
    # Admin
    #

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

    async def env(self) -> Dict:
        status, resp = await self.io.send_message(
            _m.GetEnv(),
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
    ) -> Tuple[_m.RequestReply, Optional[AsyncIterator[bytes]]]:
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
            _m.OwsRequest(
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
            # Stream remaining bytes
            return resp, self.io.stream_bytes(timeout=self._timeout)
        else:
            return resp, None

    async def api_request(
        self,
        name: str,
        path: str,
        url: str,
        target: Optional[str] = None,
        data: Optional[bytes] = None,
        delegate: bool = False,
        direct: bool = False,
        method: _m.HTTPMethod = _m.HTTPMethod.GET,
        options: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        request_id: str = "",
        debug_report: bool = False,
    ) -> Tuple[_m.RequestReply, Optional[AsyncIterator[bytes]]]:
        """ Send generic (api) request

            Exemple:
            ```
            resp, stream = await worker.api_request(
                name="OGC WFS3 (Draft)"
                path="/collections"
                url="http://foo.com/features",
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
            _m.ApiRequest(
                name=name,
                path=path,
                url=url,
                method=method,
                data=data,
                delegate=delegate,
                target=target,
                direct=direct,
                options=options,
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
            return resp, self.io.stream_bytes(timeout=self._timeout)
        else:
            return resp, None

    async def request(
        self,
        url: str,
        data: bytes,
        target: Optional[str],
        direct: bool = False,
        method: _m.HTTPMethod = _m.HTTPMethod.GET,
        headers: Optional[Dict[str, str]] = None,
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
            return resp, self.io.stream_bytes(timeout=self._timeout)
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
    ) -> Tuple[int, Optional[AsyncIterator[_m.CacheInfo]]]:
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

    async def update_cache(self) -> AsyncIterator[_m.CacheInfo]:
        """ Update projects in cache

            Return the list of cached object with their new status
        """
        logger.info("Updating cache for '%s'", self.name)
        status, resp = await self.io.send_message(
            _m.UpdateCache(),
            timeout=self._timeout,
        )

        if status != 200:
            raise WorkerError(status, resp)

        async def _stream():
            status, resp = await self.io.read_message(timeout=self._timeout)
            while status == 206:
                yield resp
                status, resp = await self.io.read_message(timeout=self._timeout)
            # Incomplete transmission ?
            if status != 200:
                raise WorkerError(status, resp)

        return _stream()

    async def clear_cache(self) -> None:
        """  Clear all items in cache
        """
        logger.info("Purging cache for '%s'", self.name)
        status, resp = await self.io.send_message(
            _m.ClearCache(),
            timeout=self._timeout,
        )
        if status != 200:
            raise WorkerError(status, resp)

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[_m.CatalogItem]:
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
