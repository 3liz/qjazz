
from io import BytesIO
from struct import pack, unpack
from typing import (
    Any,
    ByteString,
    Iterator,
)

import msgpack

from qjazz_rpc import messages


class NoDataResponse(Exception):
    pass


class Connection:
    def __init__(self):
        self._buf = BytesIO()
        self._cancelled = False

    def recv(self) -> messages.Message:
        raise NotImplementedError

    def send_bytes(self, data: ByteString):
        if self._cancelled:
            return
        size = len(data)
        self._buf.write(pack("!i", size))
        if data:
            self._buf.write(data)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    ### Synchronous Reader

    def read_message(self) -> tuple[int, Any]:
        """Read an Envelop message"""
        self._buf.seek(0)
        return self.read_next_message()

    def read_next_message(self) -> tuple[int, Any]:
        """Read an Envelop message"""
        resp = msgpack.unpackb(self.read_bytes())
        match resp:
            case (int(status), msg):
                return (status, msg)
            case 204:
                raise NoDataResponse()
            case _:
                raise ValueError(f"Unexpected response format: {resp}")

    def stream(self) -> Iterator[Any]:
        st, resp = self.read_message()
        assert st in (200, 206)
        yield resp
        if st == 200:
            return
        try:
            while True:
                st, resp = self.read_next_message()
                assert st in (200, 206)
                yield resp
        except NoDataResponse:
            pass

    def read_bytes(self) -> bytes:
        (size,) = unpack("!i", self._buf.read(4))
        data = self._buf.read(size) if size else b""
        if len(data) < size:
            buf = BytesIO()
            buf.write(data)
            remaining = size - len(data)
            while remaining > 0:
                chunk = self._buf.read(remaining)
                remaining -= len(chunk)
                buf.write(chunk)
            data = buf.getvalue()
        return data

    def stream_bytes(self) -> Iterator[bytes]:
        resp = msgpack.unpackb(self.read_bytes())
        while True:
            match resp:
                case 206:
                    yield self.read_bytes()
                    resp = msgpack.unpackb(self.read_bytes())
                    continue
                case 204:
                    break
                case _:
                    raise ValueError(f"Byte stream returned {resp}")

    def clear(self):
        self._buf.seek(0)
        self._buf.truncate(0)
