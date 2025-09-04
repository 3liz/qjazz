"""Qgis server request handler"""

import traceback

from contextlib import contextmanager
from time import time
from typing import Optional

from qgis.core import QgsFeedback
from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice
from qgis.server import QgsServerRequest, QgsServerResponse

from qjazz_contrib.core import logger

from . import messages as _m


def _to_qgis_method(method: _m.HTTPMethod) -> QgsServerRequest.Method:
    match method:
        case _m.HTTPMethod.GET:
            return QgsServerRequest.GetMethod
        case _m.HTTPMethod.HEAD:
            return QgsServerRequest.HeadMethod
        case _m.HTTPMethod.POST:
            return QgsServerRequest.PostMethod
        case _m.HTTPMethod.PUT:
            return QgsServerRequest.PutMethod
        case _m.HTTPMethod.DELETE:
            return QgsServerRequest.DeleteMethod
        case _m.HTTPMethod.PATCH:
            return QgsServerRequest.PatchMethod
        case _:
            # Other methods are not implemented
            # in QgisServerRequest
            raise ValueError(method.name)


class Request(QgsServerRequest):
    def __init__(
        self,
        url: str,
        method: QgsServerRequest.Method,
        headers: dict[str, str],
        data: Optional[bytes],
    ):
        self._data = data
        super().__init__(url, method, headers=headers)

    def data(self) -> QByteArray:
        """Override"""
        # Make sure that data is valid
        return QByteArray(self._data) if self._data else QByteArray()


# Define default chunk size to be 1Mo
DEFAULT_CHUNK_SIZE = 1024 * 1024


class Response(QgsServerResponse):
    """Adaptor to handler response

    The data is written at 'flush()' call.
    """

    def __init__(
        self,
        conn: _m.Connection,
        *,
        target: Optional[str] = None,
        co_status: Optional[int] = None,
        headers: Optional[dict] = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        cache_id: str = "",
        feedback: Optional[QgsFeedback] = None,
        header_prefix: Optional[str] = None,
    ):
        super().__init__()
        self._buffer = QBuffer()
        self._buffer.open(QIODevice.ReadWrite)
        self._finish = False
        self._conn = conn
        self._status_code = 200
        self._header_written = False
        self._headers: dict[str, str] = {}
        self._co_status = co_status
        self._timestamp = time()
        self._extra_headers: dict[str, str] = headers or {}
        self._chunk_size = chunk_size
        self._cache_id = cache_id
        self._feedback = feedback
        self._header_prefix = header_prefix or ""
        self._target = target

    # Since 3.36
    def feedback(self) -> Optional[QgsFeedback]:
        return self._feedback

    def setStatusCode(self, code: int) -> None:
        if not self._header_written:
            self._status_code = code
        else:
            logger.error("Cannot set status code after header written")

    def statusCode(self) -> int:
        return self._status_code

    def finish(self) -> None:
        """Terminate the request"""
        self._finish = True
        self.flush()

    def _send_response(self):
        """Send response"""
        self._headers.update(self._extra_headers)

        # Return reply
        _m.send_reply(
            self._conn,
            _m.RequestReply(
                target=self._target,
                status_code=self._status_code,
                headers=[(f"{self._header_prefix}{k}", v) for k, v in self._headers.items()],
                checkout_status=self._co_status,
                cache_id=self._cache_id,
            ),
        )
        self._header_written = True

    @contextmanager
    def _error(self):
        try:
            yield
        except Exception:
            logger.critical(traceback.format_exc())
            self.sendError(500)

    def flush(self) -> None:
        """Write the data to the queue
        and flush the socket

        Headers will be written at the first call to flush()
        """
        self._buffer.seek(0)
        bytes_avail = self._buffer.bytesAvailable()

        if self._finish and bytes_avail and not self._header_written:
            # Make sure that we have Content-length set
            self._headers["Content-Length"] = f"{bytes_avail}"

        if not self._header_written:
            # Send response
            self._send_response()

        # Send data as chunks
        data = memoryview(self._buffer.data())
        MAX_CHUNK_SIZE = self._chunk_size
        chunks = (data[i : i + MAX_CHUNK_SIZE] for i in range(0, bytes_avail, MAX_CHUNK_SIZE))
        for chunk in chunks:
            logger.trace("Sending chunk of %s bytes", len(chunk))
            _m.send_chunk(self._conn, chunk)

        if self._finish:
            # Send sentinel to signal end of data
            logger.trace("Sending final chunk")
            _m.send_chunk(self._conn, b"")

        self._buffer.buffer().clear()

    def header(self, key: str) -> str:
        return self._headers.get(key) or ""

    def headers(self) -> dict[str, str]:
        return self._headers

    def io(self) -> QIODevice:
        return self._buffer

    def data(self) -> QByteArray:
        return self._buffer.data()

    def setHeader(self, key: str, value: str) -> None:
        if not self._header_written:
            self._headers[key] = value
        else:
            logger.error("Cannot set header after header written")

    def removeHeader(self, key: str) -> None:
        self._headers.pop(key, None)

    def sendError(self, code: int, message: Optional[str] = None) -> None:
        try:
            if not self._header_written:
                logger.error("Qgis server error: %s (%s)", message, code)
                self._status_code = code
                self.truncate()
                self._buffer.write(message.encode() if message else b"")
                self.finish()
            else:
                logger.error("Cannot set error after header written")
        except Exception:
            logger.critical("Unrecoverable exception:\n%s", traceback.format_exc())

    def clear(self) -> None:
        self._headers = {}
        self.truncate()

    def headersSent(self) -> bool:
        return self._header_written

    def truncate(self) -> None:
        """Truncate buffer"""
        self._buffer.seek(0)
        self._buffer.buffer().clear()
