#
# Qgis server request operations
#
from urllib.parse import urlunsplit

from typing_extensions import (
    Optional,
    Tuple,
    Dict,
    assert_never,
)
from multiprocessing.connection import Connection

from qgis.server import (
    QgsServer,
    QgsServerRequest,
    QgsServerException,
)

from py_qgis_contrib.core import logger
from py_qgis_cache import (
    CacheManager,
    CacheEntry,
    CheckoutStatus,
)

from . import messages as _m
from .config import WorkerConfig
from .requests import Request, Response, _to_qgis_method
from .serverapi import ROOT_DELEGATE

Co = CheckoutStatus


#
# Server Request
#
QGIS_MISSING_PROJECT_ERROR_MSG = "No project defined"


def handle_ows_request(
    conn: Connection,
    msg: _m.OwsRequest,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
    cache_id: str = "",
):
    """ Handle OWS request
    """
    if not msg.target:
        exception = QgsServerException(QGIS_MISSING_PROJECT_ERROR_MSG, 400)
        response = Response(conn)
        response.write(exception)
        response.finish()
        return

    if msg.debug_report and not _process:
        _m.send_reply(conn, "No report available", 409)
        return

    # Rebuild URL for Qgis server
    url = msg.url + f"?SERVICE={msg.service}&REQUEST={msg.request}"
    if msg.version:
        url += f"&VERSION={msg.version}"
    if msg.options:
        url += f"&{msg.options}"

    _handle_generic_request(
        url,
        msg.target,
        msg.direct,
        None,
        QgsServerRequest.GetMethod,
        msg.headers,
        conn,
        server,
        cm,
        config,
        _process if msg.debug_report else None,
        cache_id=cache_id,
    )


def handle_api_request(
    conn: Connection,
    msg: _m.ApiRequest,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
    cache_id: str = "",
):
    """ Handle api request
    """
    try:
        method = _to_qgis_method(msg.method)
    except ValueError:
        _m.send_reply(conn, "HTTP Method not supported", 405)
        return

    if msg.debug_report and not _process:
        _m.send_reply(conn, "No report available", 409)
        return

    # Rebuild URL for Qgis server
    url = f"{msg.url.rstrip('/')}{ROOT_DELEGATE}/{msg.path.lstrip('/')}"
    if msg.options:
        url += f"?{msg.options}"

    assert msg.headers is not None
    headers = msg.headers

    # Pass api name as header
    # to api delegate
    headers['x-qgis-api'] = msg.name

    _handle_generic_request(
        url,
        msg.target,
        msg.direct,
        msg.data,
        method,
        msg.headers,
        conn,
        server,
        cm,
        config,
        _process if msg.debug_report else None,
        cache_id=cache_id,
    )


def handle_generic_request(
    conn: Connection,
    msg: _m.Request,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
    cache_id: str = "",
):
    try:
        method = _to_qgis_method(msg.method)
    except ValueError:
        _m.send_reply(conn, "HTTP Method not supported", 405)
        return

    if msg.debug_report and not _process:
        _m.send_reply(conn, "No report available", 409)
        return

    _handle_generic_request(
        msg.url,
        msg.target,
        msg.direct,
        msg.data,
        msg.headers,
        method,
        conn,
        server,
        cm,
        config,
        _process if msg.debug_report else None,
        cache_id=cache_id,
    )


def _handle_generic_request(
    url: str,
    target: Optional[str],
    allow_direct: str,
    data: Optional[bytes],
    method: QgsServerRequest.Method,
    headers: Dict[str, str],
    conn: Connection,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
    cache_id: str
):
    """ Handle generic Qgis request
    """
    if target:
        co_status, entry = request_project_from_cache(
            conn,
            cm,
            config,
            target=target,
            allow_direct=allow_direct,
        )

        if not entry or co_status == Co.REMOVED:
            return

        project = entry.project
        response = Response(
            conn,
            co_status,
            last_modified=entry.last_modified,
            chunk_size=config.max_chunk_size,
            _process=_process,
        )
        # See https://github.com/qgis/QGIS/pull/9773
        server.serverInterface().setConfigFilePath(project.fileName())
    else:
        project = None
        response = Response(conn, _process=_process, cache_id=cache_id)

    request = Request(url, method, headers, data=data)
    server.handleRequest(request, response, project=project)


def request_project_from_cache(
    conn: Connection,
    cm: CacheManager,
    config: WorkerConfig,
    target: str,
    allow_direct: bool,
) -> Tuple[CheckoutStatus, Optional[CacheEntry]]:
    """ Handle project retrieval from cache
    """
    try:
        entry = None
        url = cm.resolve_path(target, allow_direct)
        md, co_status = cm.checkout(url)
        match co_status:
            case Co.NEEDUPDATE:
                # This is configuration dependent
                # Projects are updated on request only
                # if the configuration allow it
                # This is not a good idea to keep an outdated
                # project in cache since the associated resources
                # may have chanced. But in the other hand it could
                # prevents access while project's ressource are
                # not fully updated
                if config.reload_outdated_project_on_request:
                    entry, co_status = cm.update(md, co_status)
                else:
                    entry = md
            case Co.UNCHANGED:
                entry = md
            case Co.NEW:
                if config.load_project_on_request:
                    if config.max_projects <= len(cm):
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            target,
                        )
                        _m.send_reply(conn, "Max object reached on server", 403)
                    else:
                        entry, co_status = cm.update(md, co_status)
                else:
                    logger.error("Request for loading NEW project '%s'", md.uri)
                    _m.send_reply(conn, target, 403)
            case Co.REMOVED:
                # Do not serve a removed project
                # Since layer's data may not exists
                # anymore
                logger.warning("Requested removed project: %s", md.uri)
                _m.send_reply(conn, target, 410)
                entry = md
            case Co.NOTFOUND:
                logger.error("Requested project not found: %s", urlunsplit(url))
                _m.send_reply(conn, target, 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)
    except CacheManager.StrictCheckingFailure as err:
        _m.send_reply(conn, str(err), 422)

    return co_status, entry
