
from pathlib import Path

from typing_extensions import Dict

from qgis.PyQt.QtCore import QByteArray, QFile, QIODevice
from qgis.server import QgsServerResponse

from qjazz_contrib.core import logger


class QgsServerFileResponse(QgsServerResponse):
    """ Implement a QgsServerResponse that writes
        directly to file
    """

    def __init__(self, path: Path | str):
        super().__init__()
        self._headers: Dict[str, str] = {}
        self._status_code = 200
        self._output = QFile(str(path))

        if not self.open(QIODevice.WriteOnly):
            error = self._output.error()
            raise RuntimeError(f"Failed to open '{path}': error {error}")

    def clear(self) -> None:
        self._headers = {}

    def data(self) -> QByteArray:
        return QByteArray()

    def finish(self) -> None:
        self._output.flush()
        self._output.close()

    def flush(self) -> None:
        self._output.flush()

    def header(self, key: str) -> str:
        return self._headers.get(key, "")

    def headers(self) -> Dict[str, str]:
        return self._headers

    def headersSent(self) -> bool:
        return not self._output.isOpen()

    def io(self) -> QIODevice:
        return self._output

    def removeHeader(self, key: str) -> None:
        self._headers.pop(key, None)

    def sendError(self, code: int, message: str) -> None:
        self._status_code = code
        logger.error("Server response error %s: %s", code, message)

    def setHeader(self, key: str, value: str) -> None:
        self._headers[key] = value

    def setStatusCode(self, code: int) -> None:
        self._status_code = code

    def statusCode(self) -> int:
        return self._status_code

    def truncate(self) -> None:
        self._output.resize(0)
