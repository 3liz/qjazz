import asyncio

from time import time

from typing_extensions import Iterator, List, Optional

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_precondition

from .channel import Channel
from .config import BackendConfig, ConfigProto

#
# Channels
#


async def _init_channel(name: str, backend: BackendConfig) -> Channel:
    """  Initialize channel from backend
    """
    chan = Channel(name, backend)
    await chan.connect()
    return chan


class Channels:
    """ Handle channels
    """

    def __init__(self, conf: ConfigProto):
        self._conf = conf
        self._channels: List[Channel] = []
        self._last_modified = time()

    @property
    def backends(self) -> Iterator[Channel]:
        return iter(self._channels)

    @property
    def last_modified(self) -> float:
        return self._last_modified

    def is_modified_since(self, timestamp: float) -> bool:
        return self._last_modified > timestamp

    async def init_channels(self):
        # Initialize channels
        logger.info("Reconfiguring channels")
        channels = await asyncio.gather(
            *(_init_channel(name, be) for name, be in self._conf.backends.items()),
        )
        # Close previous channels
        if self._channels:
            background_tasks = set()
            logger.trace("Closing current channels")
            # Run in background since we do want to wait for
            # grace period before
            task = asyncio.create_task(self.close(with_grace_period=True))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)
        logger.trace("Setting new channels")
        self._channels = channels
        self._last_modified = time()

    async def close(self, with_grace_period: bool = False):
        channels = self._channels
        self._channels = []
        await asyncio.gather(*(chan.close(with_grace_period) for chan in channels))

    def get_backend(self, name: str) -> Optional[BackendConfig]:
        return self._conf.backends.get(name)

    async def add_backend(self, name: str, backend: BackendConfig):
        """ Add new backend (equivalent to POST)
        """
        assert_precondition(name not in self._conf.backends)
        self._conf.backends[name] = backend
        self._channels.append(await _init_channel(name, backend))

    def remove_backend(self, name: str) -> bool:
        """ Delete a specific backend from the list
        """
        backend = self._conf.backends.pop(name, None)
        if not backend:
            return False

        def _close():
            background_tasks = set()
            for chan in self._channels:
                if chan.address == backend.address:
                    task = asyncio.create_task(chan.close(with_grace_period=True))
                    background_tasks.add(task)
                    task.add_done_callback(background_tasks.discard)
                else:
                    yield chan
        self._channels = list(_close())
        return True

    def channel_by_name(self, name: str) -> Optional[Channel]:
        """ Return a channel by its name
        """
        for channel in self._channels:
            if channel.name == name:
                return channel
        else:
            return None
