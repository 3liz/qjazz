import asyncio
import os

from io import BytesIO
from pathlib import Path
from struct import pack, unpack
from typing import (
    Any,
    AsyncIterator,
)

import msgpack

from pydantic import BaseModel

from .. import messages  # noqa F401
from ..messages import Message


class NoDataResponse(Exception):
    pass


class Pipe:
    """ Wrapper for Connection object that allow reading asynchronously
    """
    def __init__(self, proc: asyncio.subprocess.Process):
        if proc.stdin is None:
            raise ValueError("Invalid StreamWriter")
        if proc.stdout is None:
            raise ValueError("Invalid StreamReader")
        self._stdin = proc.stdin
        self._stdout = proc.stdout

    async def put_message(self, message: Message):
        if isinstance(message, BaseModel):
            data = msgpack.packb(message.model_dump(mode='json'))
        else:
            data = msgpack.packb(message)
        self._stdin.write(pack('!i', len(data)))
        self._stdin.write(data)
        await self._stdin.drain()

    async def drain(self):
        """ Pull out all remaining data from pipe
        """
        size = unpack('!i', await self._stdout.readexactly(4))
        if size > 0:
            _ = await self._stdout.read(size)

    async def read_message(self) -> tuple[int, Any]:
        """ Read an Envelop message
        """
        resp = msgpack.unpackb(await self.read_bytes())
        match resp:
            case (int(status), msg):
                return (status, msg)
            case 204:
                raise NoDataResponse()
            case _:
                raise ValueError(f"Unexpected response format: {resp}")

    async def read_bytes(self) -> bytes:
        size, = unpack('!i', await self._stdout.read(4))
        data = await self._stdout.read(size) if size else b''
        if len(data) < size:
            buf = BytesIO()
            buf.write(data)
            remaining = size - len(data)
            while remaining > 0:
                chunk = await self._stdout.read(remaining)
                remaining -= len(chunk)
                buf.write(chunk)
            data = buf.getvalue()
        return data

    async def stream_bytes(self) -> AsyncIterator[bytes]:
        resp = msgpack.unpackb(await self.read_bytes())
        while True:
            match resp:
                case 206:
                    yield await self.read_bytes()
                    resp = msgpack.unpackb(await self.read_bytes())
                    continue
                case 204:
                    break
                case _:
                    raise ValueError(f"Byte stream returned {resp}")

    async def send_message(self, msg: Message) -> tuple[int, Any]:
        await self.put_message(msg)
        return await self.read_message()

#
# Rendez Vous
#


class RendezVous:

    def __init__(self, path: Path):
        self._path = path
        self._done = asyncio.Event()
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def path(self) -> Path:
        return self._path

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    def start(self):
        if self._task:
            raise RuntimeError("Rendez vous already started")

        async def _listen():
            # Open a named pipe and read continuously from it.
            #
            #    Writer just need to open the path
            #    in binary write mode (rb)
            #
            #    ```
            #    rendez_vous = path.open('wb')
            #    ```
            self._running = True

            path = self.path.as_posix()
            os.mkfifo(path)
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            avail = asyncio.Event()
            asyncio.get_running_loop().add_reader(fd, avail.set)
            while self._running:
                await avail.wait()
                try:
                    match os.read(fd, 1024):
                        case b'\x00':  # DONE
                            self._done.set()
                        case b'\x01':  # BUSY
                            self._done.clear()
                except BlockingIOError:
                    pass
                avail.clear()

        self._task = asyncio.create_task(_listen())

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def busy(self) -> bool:
        return not self.done

    async def wait(self):
        await self._done.wait()
