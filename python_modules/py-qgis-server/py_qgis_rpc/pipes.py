import asyncio
import os
import pickle  # nosec

from io import BytesIO
from pathlib import Path
from struct import pack, unpack

from typing_extensions import (
    Any,
    AsyncIterator,
    Tuple,
)

from .messages import (
    Message,
    RequestReport,
    cast_into,
)


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
        data = pickle.dumps(message)
        self._stdin.write(pack('!i', len(data)))
        self._stdin.write(data)
        await self._stdin.drain()

    async def drain(self):
        """ Pull out all remaining data from pipe
        """
        size = unpack('!i', await self._stdout.readexactly(4))
        if size > 0:
            _ = await self._stdout.read(size)

    async def read_report(self) -> RequestReport:
        return cast_into(
            pickle.loads(await self.read_bytes()),  # nosec
            RequestReport,
        )

    async def read_message(self) -> Tuple[int, Any]:
        """ Read an Envelop message
        """
        resp = pickle.loads(await self.read_bytes())  # nosec
        match resp:
            case (int(status), msg):
                return (status, msg)
            case _:
                raise ValueError(f"Expecting (status, msg), not {resp}")


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
        b = await self.read_bytes()
        while b:
            yield b
            b = await self.read_bytes()

    async def send_message(self, msg: Message) -> Tuple[int, Any]:
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
        self._task = asyncio.create_task(self._listen())

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def busy(self) -> bool:
        return not self.done

    async def wait(self):
        await self._done.wait()

    async def _listen(self):
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
