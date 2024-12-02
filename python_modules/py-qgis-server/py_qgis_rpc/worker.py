import asyncio
import os
import signal
import sys

from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import JsonValue
from typing_extensions import (
    AsyncIterator,
    Dict,
    Optional,
    Tuple,
    cast,
)

from py_qgis_contrib.core import logger

from . import messages as _m
from .config import WorkerConfig
from .pipes import Pipe, RendezVous

START_TIMEOUT = 5


class WorkerError(Exception):
    def __init__(self, code: int, details: JsonValue = ""):
        self.code = code
        self.details = str(details)


class Worker:
    """ Worker stub api

        *WARNING*: There is a race condition between
        tasks: use a lock mecanism to protect
        concurrent calls.
    """

    def __init__(self, config: WorkerConfig, name: Optional[str] = None):
        self._name = name or ""
        self._worker_conf = config
        self._timeout = config.process_timeout
        self._tmpdir = TemporaryDirectory(prefix="qserv_")
        self._rendez_vous = RendezVous(Path(self._tmpdir.name, "_rendez_vous"))
        self._process: asyncio.subprocess.Process | None = None
        self._terminate_task: asyncio.Task | None = None

    @property
    def config(self) -> WorkerConfig:
        return self._worker_conf

    async def cancel(self):
        """ Send a SIGHUP signal to to the process
        """
        logger.trace("Cancelling job: %s (done: %s)", self.pid, self.task_done)
        if not (self._process is None or self.task_done):
            self._process.send_signal(signal.SIGHUP)
            # Pull stream from current task
            # Handle timeout, since the main reason
            # for cancelling may be a stucked or
            # long polling response.
            await self.consume_until_task_done()

    @property
    def name(self) -> str:
        return self._name

    @property
    def task_done(self) -> bool:
        """ Return true if there is no processing
            at hand
        """
        return not self._rendez_vous.busy

    @property
    def is_alive(self):
        return self._process and self._process.returncode is None

    async def quit(self, grace_period: Optional[int] = None):
        """ Send a quit message
        """
        if not self.is_alive:
            return

        self._rendez_vous.stop()
        if grace_period:
            try:
                async with asyncio.timeout(grace_period):
                    await self.io.send_message(_m.QuitMsg())
                    await self.join()
            except TimeoutError:
                self.terminate()
        else:
            status, _ = await self.io.send_message(_m.QuitMsg())
            if status != 200:
                raise WorkerError(status, "Message failure (QUIT)")
            # Wait for process to finish
            await self.join()

    async def consume_until_task_done(self):
        """ Consume all remaining data that may be send
            by the worker task.
            This is required if a client abort the request
            in the middle.
        """
        while self._rendez_vous.busy:
            try:
                await asyncio.wait_for(self.io.drain(), 1)
            except TimeoutError:
                pass

    async def update_config(self, worker_conf: WorkerConfig):
        self._worker_conf = worker_conf
        status, resp = await self.io.send_message(
            _m.PutConfigMsg(
                config={
                    'logging': {'level': logger.log_level()},
                    'worker': worker_conf.model_dump(),
                },
            ),
        )
        if status != 200:
            raise WorkerError(status, resp)
        # Update timeout config
        self._timeout = self.config.process_timeout
        logger.trace(f"Updated config for worker '{self.name}'")

    async def start(self):
        """ Start the worker QGIS subprocess
        """
        logger.debug("Starting worker %s", self.name)
        # Start rendez-vous fifo
        self._rendez_vous.start()

        # Prepare environment
        env = os.environ.copy()
        env.update(
            CONF_WORKER=self.config.model_dump_json(),
            CONF_LOGGING__LEVEL=logger.log_level().name,
            RENDEZ_VOUS=self._rendez_vous.path,
        )

        # Run subprocess
        # This is slower that `fork` but
        # allow for solid asynchronous I/0 handling
        self._process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "py_qgis_rpc.process", self._name,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            await asyncio.wait_for(self._rendez_vous.wait(), START_TIMEOUT)
        except TimeoutError:
            raise RuntimeError(
                f"Failed to start worker <return code: {self._process.returncode}>",
            ) from None

    def terminate(self):
        """ Terminate the subprocess """
        if not self.is_alive:
            return

        self._rendez_vous.stop()

        proc = self._process

        # Run the termination in its own task
        async def _term():
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10)
            except TimeoutError:
                logger.warning("Worker '%s' not terminated, kill forced", self._name)
                proc.kill()

        self._terminate_task = asyncio.create_task(_term())

    async def join(self, timeout: Optional[int] = None):
        if not self._process:
            return
        if timeout:
            await asyncio.wait_for(self._process.wait(), timeout)
        else:
            await self._process.wait()

    @cached_property
    def io(self) -> Pipe:
        if not self._process:
            raise RuntimeError("Process no initialized")
        return Pipe(self._process)

    # ================
    # API stubs
    # ================

    #
    # Admin
    #

    async def ping(self, echo: str) -> str:
        """  Send ping with echo string
        """
        status, resp = await self.io.send_message(_m.PingMsg(echo=echo))
        if status != 200:
            raise WorkerError(status, resp)
        return cast(str, resp)

    async def env(self) -> Dict:
        status, resp = await self.io.send_message(_m.GetEnvMsg())
        if status != 200:
            raise WorkerError(status, resp)

        return cast(Dict, resp)

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
            _m.OwsRequestMsg(
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
        )

        # Request failed before reaching Qgis server
        if status != 200:
            raise WorkerError(status, resp)

        reply = _m.cast_into(resp, _m.RequestReply)

        if reply.chunked:
            return reply, self.io.stream_bytes()
        else:
            return reply, None

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
            _m.ApiRequestMsg(
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
        )
        # Request failed before reaching Qgis server
        if status != 200:
            raise WorkerError(status, resp)

        reply = _m.cast_into(resp, _m.RequestReply)

        if reply.chunked:
            return reply, self.io.stream_bytes()
        else:
            return reply, None

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
            _m.RequestMsg(
                url=url,
                method=method,
                data=data,
                target=target,
                direct=direct,
                headers=headers or {},
                request_id=request_id,
                debug_report=debug_report,
            ),
        )
        # Request failed before reaching Qgis server
        if status != 200:
            raise WorkerError(status, resp)

        reply = _m.cast_into(resp, _m.RequestReply)

        if reply.chunked:
            return reply, self.io.stream_bytes()
        else:
            return reply, None

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
            _m.CheckoutProjectMsg(uri=uri, pull=pull),
        )
        if status != 200:
            raise WorkerError(status, resp)
        return _m.cast_into(resp, _m.CacheInfo)

    async def drop_project(self, uri: str) -> _m.CacheInfo:
        """ Drop project from cache
        """
        status, resp = await self.io.send_message(
            _m.DropProjectMsg(uri=uri),
        )
        if status != 200:
            raise WorkerError(status, resp)
        return _m.cast_into(resp, _m.CacheInfo)

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
            _m.ListCacheMsg(status_filter=status_filter),
        )

        if status != 200:
            raise WorkerError(status, resp)

        count = cast(int, resp)

        if count > 0:
            async def _stream():
                status, resp = await self.io.read_message()
                while status == 206:
                    yield _m.cast_into(resp, _m.CheckoutStatus)
                    status, resp = await self.io.read_message()
            # Incomplete transmission ?
            if status != 200:
                raise WorkerError(status, resp)

            return count, _stream()
        else:
            return count, None

    async def update_cache(self) -> AsyncIterator[_m.CacheInfo]:
        """ Update projects in cache

            Return the list of cached object with their new status
        """
        logger.info("Updating cache for '%s'", self.name)
        status, resp = await self.io.send_message(_m.UpdateCacheMsg())

        if status != 200:
            raise WorkerError(status, resp)

        async def _stream():
            status, resp = await self.io.read_message()
            while status == 206:
                yield _m.cast_into(resp, _m.CacheInfo)
                status, resp = await self.io.read_message()
            # Incomplete transmission ?
            if status != 200:
                raise WorkerError(status, resp)

        return _stream()

    async def clear_cache(self) -> None:
        """  Clear all items in cache
        """
        logger.info("Purging cache for '%s'", self.name)
        status, resp = await self.io.send_message(_m.ClearCacheMsg())
        if status != 200:
            raise WorkerError(status, resp)

    async def catalog(self, location: Optional[str] = None) -> AsyncIterator[_m.CatalogItem]:
        """ Return all projects availables

            If location is set, returns only projects availables for
            this particular location
        """
        status, resp = await self.io.send_message(_m.CatalogMsg(location=location))
        if status != 200:
            raise WorkerError(status, str(resp))

        async def _stream():
            status, item = await self.io.read_message()
            while status == 206:
                yield _m.cast_into(resp, _m.CatalogItem)
                status, item = await self.io.read_message()
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
            _m.GetProjectInfoMsg(uri=uri),
        )
        if status != 200:
            raise WorkerError(status, resp)

        return _m.cast_into(resp, _m.ProjectInfo)

    #
    # Plugins
    #
    async def list_plugins(self) -> AsyncIterator[_m.PluginInfo]:
        """ List projects in cache

            Return 2-tuple where first element is the number
            of loaded plugins and the second elemeent an async
            iterator yielding PluginInfo items
        """
        status, resp = await self.io.send_message(_m.PluginsMsg())
        if status != 200:
            raise WorkerError(status, resp)

        status, resp = await self.io.read_message()
        while status == 206:
            yield _m.cast_into(resp, _m.PluginInfo)
            status, resp = await self.io.read_message()
        # Incomplete transmissions !
        if status != 200:
            raise WorkerError(status, resp)

    #
    # Test
    #
    async def execute_test(self, delay: int) -> None:
        """  Send ping with echo string
        """
        status, resp = await self.io.send_message(_m.TestMsg(delay=delay))
        if status != 200:
            raise WorkerError(status, resp)
