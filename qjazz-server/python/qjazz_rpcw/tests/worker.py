#
# Worker implementation for tests
#

import asyncio
import os
import signal
import sys

from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import JsonValue

from qjazz_contrib.core import logger

from ..config import QgisConfig
from .rendezvous import (
    NoDataResponse,  # noqa F401
    Pipe,
    RendezVous,
)
from .rendezvous import messages as _m

START_TIMEOUT = 20


class WorkerError(Exception):
    def __init__(self, code: int, details: JsonValue = ""):
        self.code = code
        self.details = str(details)


class Worker:

    def __init__(self, config: QgisConfig, num_processes: int = 1):
        self._name = "Test"
        self._conf = config
        self._tmpdir = TemporaryDirectory(prefix="qserv_")
        self._rendez_vous = RendezVous(Path(self._tmpdir.name, "_rendez_vous"))
        self._process: asyncio.subprocess.Process | None = None
        self._started = False

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

    async def wait_ready(self):
        await self._rendez_vous.wait()

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

    async def update_config(self, conf: QgisConfig):
        self._conf = conf
        status, resp = await self.io.send_message(
            _m.PutConfigMsg(
                config={
                    'logging': {'level': logger.log_level()},
                    'worker': {'qgis': conf.model_dump()},
                },
            ),
        )
        if status != 200:
            raise WorkerError(status, resp)
        logger.trace(f"Updated config for worker '{self.name}'")

    async def start(self):
        """ Start the worker QGIS subprocess
        """
        if self._started:
            return

        self._started = True

        logger.debug("Starting worker %s", self.name)
        # Start rendez-vous fifo
        self._rendez_vous.start()

        # Prepare environment
        env = os.environ.copy()
        env.update(
            CONF_WORKER__QGIS=self._conf.model_dump_json(),
            CONF_LOGGING__LEVEL=logger.log_level().name,
            RENDEZ_VOUS=self._rendez_vous.path,
        )

        self._process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "qjazz_rpcw.main", self._name,
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

    async def terminate(self):
        """ Terminate the subprocess """
        if not self.is_alive:
            return

        self._rendez_vous.stop()
        self._process.terminate()
        try:
            await asyncio.wait_for(self._process.wait(), 10)
        except TimeoutError:
            logger.warning("Worker '%s' not terminated, kill forced", self._name)
            self._process.kill()

    @cached_property
    def io(self) -> Pipe:
        if not self._process:
            raise RuntimeError("Process no initialized")
        return Pipe(self._process)
