#
# Log QGIS request
#
from typing import Optional, Protocol

from qjazz_contrib.core import logger
from qjazz_contrib.core.timer import Instant

from .messages import Connection, Response, send_reply


class QgsServerResponse(Protocol):
    def statusCode(self) -> int: ...


class Report(Response):
    req_id: str
    service: str
    request: str
    target: str
    target_hits: int
    response_status: int
    response_time: int


class Monitor:
    def __init__(self, conn: Optional[Connection]) -> None:
        self._instant = Instant()
        self._conn = conn

    def accept(
        self,
        request_id: str,
        project_location: str | None,
    ):
        logger.info(
            "QGIS Request accepted\tMAP:%s\tREQ_ID:%s",
            project_location or "<notset>",
            request_id,
        )

    def log(
        self,
        request_id: str,
        service: str,
        request: str,
        target: str,
        resp: QgsServerResponse,
        hits: int,
    ):
        if self._conn:
            data = Report(
                req_id=request_id,
                service=service,
                request=request,
                target=target,
                target_hits=hits,
                response_status=resp.statusCode(),
                response_time=self._instant.elapsed_ms,
            )

            logger.log_req(
                "[REQ_ID:%s]\t%s\tservice=%s\trequest=%s\t%s\t%s",
                data.req_id,
                data.target,
                data.service,
                data.request,
                data.response_status,
                data.response_time,
            )

            # Send report
            send_reply(self._conn, data)
        else:
            logger.log_req(
                "[REQ_ID:%s]\t%s\tservice=%s\trequest=%s\t%s\t%s",
                request_id,
                target,
                service,
                request,
                resp.statusCode(),
                self._instant.elapsed_ms,
            )
