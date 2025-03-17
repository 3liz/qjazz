#
# Log QGIS request
#
from qgis.server import QgsServerResponse

from qjazz_contrib.core import logger
from qjazz_contrib.core.models import JsonModel
from qjazz_contrib.core.timer import Instant


class Data(JsonModel):
    r_id: str
    service: str
    request: str
    target: str
    status_code: int
    time: int


class Log:
    def __init__(self) -> None:
        self._instant = Instant()

    def log(
        self,
        request_id: str,
        service: str,
        request: str,
        target: str,
        resp: QgsServerResponse,
    ):
        logger.log_req(
            Data(
                r_id=request_id,
                service=service,
                request=request,
                target=target,
                status_code=resp.statusCode(),
                time=self._instant.elapsed_ms,
            ).model_dump_json(),
        )
