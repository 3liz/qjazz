""" Qgis server request handler
"""
import traceback

from contextlib import contextmanager
from time import time
from datetime import datetime, timezone
from typing_extensions import (
    Optional,
    Dict,
)
from multiprocessing.connection import Connection

from qgis.PyQt.QtCore import QBuffer, QIODevice, QByteArray
from qgis.server import (
    QgsServerRequest,
    QgsServerResponse,
)

from py_qgis_contrib.core import logger
from py_qgis_project_cache import CheckoutStatus

from . import messages as _m


# RFC822
WEEKDAYS = [
    "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"
]


def _to_rfc822(timestamp):
    """ Convert timestamp in seconds
        to rfc 822 Last-Modified HTTP format
    """
    dt = datetime.fromtimestamp(timestamp).astimezone(timezone.utc)
    dayname = WEEKDAYS[dt.weekday()]
    return (
        f"{dayname}, {dt.day:02} {dt.month:02} {dt.year:04} "
        f"{dt.hour:02}:{dt.minute:02}:{dt.second:02} GMT"
    )


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
        headers: Dict[str, str],
        data: bytes,
    ):
        self._data = data
        super().__init__(url, method, headers=headers)

    def data(self) -> QByteArray:
        """ Override
        """
        # Make sure that data is valid
        return QByteArray(self._data) if self._data else QByteArray()


# Define maximum chunk size to be 64Ko
# This will be in accordance with gRPC recommended
# chunk size
MAX_CHUNK_SIZE = 1024 * 64


class Response(QgsServerResponse):
    """ Adaptor to handler response

        The data is written at 'flush()' call.
    """

    def __init__(
            self,
            conn: Connection,
            co_status: Optional[CheckoutStatus] = None,
            last_modified: Optional[int] = None,
            _process: Optional = None,
    ):
        super().__init__()
        self._buffer = QBuffer()
        self._buffer.open(QIODevice.ReadWrite)
        self._finish = False
        self._conn = conn
        self._status_code = 200
        self._header_written = False
        self._headers = {}
        self._co_status = co_status
        self._process = _process
        self._timestamp = time()
        self._last_modified = last_modified

        if self._process:
            self._memory = self._process.memory_info().rss

    def _send_report(self):
        """ Send a request report
            after the last chunk of data
        """
        if self._process:
            memory = self._process.memory_info().rss - self._memory
        else:
            memory = None

        logger.debug(">>> Sending request report")
        self._conn.send(
            _m.RequestReport(
                memory=memory,
                timestamp=self._timestamp,
                duration=time() - self._timestamp,
            )
        )

    def setStatusCode(self, code: int) -> None:
        if not self._header_written:
            self._status_code = code
        else:
            logger.error("Cannot set status code after header written")

    def statusCode(self) -> int:
        return self._status_code

    def finish(self) -> None:
        """ Terminate the request
        """
        self._finish = True
        self.flush()

    def _send_response(self, data: bytes, chunked: bool = False):
        """ Send response
        """
        if self._last_modified:
            self._headers['Last-Modified'] = _to_rfc822(self._last_modified)

        # Return reply in Envelop
        _m.send_reply(
            self._conn,
            _m.RequestReply(
                status_code=self._status_code,
                headers=self._headers,
                data=data,
                checkout_status=self._co_status,
                chunked=chunked,
            )
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
        """ Write the data to the queue
            and flush the socket

            Headers will be written at the first call to flush()
        """
        self._buffer.seek(0)
        bytes_avail = self._buffer.bytesAvailable()

        if self._finish and bytes_avail and not self._header_written:
            # Make sure that we have Content-length set
            self._headers['Content-Length'] = bytes_avail

        data = bytes(self._buffer.data())

        # Take care of the logic: if finish and not handler.header_written then there is no
        # chunk following
        chunked = not self._finish or self._header_written

        if bytes_avail > MAX_CHUNK_SIZE:
            chunked = True
            bytes_avail = MAX_CHUNK_SIZE

        chunks = (data[i:i+MAX_CHUNK_SIZE] for i in range(0, bytes_avail, MAX_CHUNK_SIZE))

        if not self._header_written:
            # Send headers with first chunk of data
            chunk = next(chunks) if bytes_avail else data
            logger.debug("Sending response (chunked: %s), size: %s", chunked, len(chunk))
            self._send_response(chunk, chunked)

        if chunked:
            for chunk in chunks:
                logger.debug("Sending chunk of %s bytes", len(chunk))
                self._conn.send_bytes(chunk)

        if self._finish:
            if chunked:
                # Send sentinel to signal end of data
                self._conn.send_bytes(b'')
            # Send final report
            self._send_report()

        self._buffer.buffer().clear()

    def header(self, key: str) -> str:
        return self._headers.get(key)

    def headers(self) -> Dict[str, str]:
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
                self._send_response(message or "")
                self._finish = True
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
        """ Truncate buffer
        """
        self._buffer.seek(0)
        self._buffer.buffer().clear()
