#
# Qgis server request operations
#
from urllib.parse import urlunsplit

import psutil

from typing_extensions import Dict, Optional, Tuple, assert_never, cast

from qgis.core import QgsFeedback
from qgis.server import QgsServer, QgsServerException, QgsServerRequest

from qjazz_cache.prelude import CacheEntry, CacheManager, CheckoutStatus, ProjectMetadata
from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.utils import to_rfc822

from . import messages as _m
from .config import QgisConfig
from .delegate import ROOT_DELEGATE
from .requests import Request, Response, _to_qgis_method

Co = CheckoutStatus


#
# Server Request
#
QGIS_MISSING_PROJECT_ERROR_MSG = "No project defined"


def handle_ows_request(
    conn: _m.Connection,
    msg: _m.OwsRequestMsg,
    server: QgsServer,
    cm: CacheManager,
    config: QgisConfig,
    process: Optional[psutil.Process],
    *,
    cache_id: str = "",
    feedback: QgsFeedback,
):
    """ Handle OWS request
    """
    if not msg.target:
        exception = QgsServerException(QGIS_MISSING_PROJECT_ERROR_MSG, 400)
        response = Response(conn)
        response.write(exception)
        response.finish()
        return

    if msg.debug_report and not process:
        _m.send_reply(conn, "No report available", 409)
        return

    # Rebuild URL for Qgis server
    url = f"{msg.url or ''}?SERVICE={msg.service}&REQUEST={msg.request}"
    if msg.version:
        url += f"&VERSION={msg.version}"
    if msg.options:
        url += f"&{msg.options}"

    _handle_generic_request(
        url,
        msg.target,
        msg.direct,
        None,  # data
        QgsServerRequest.GetMethod,
        msg.headers,
        conn,
        server,
        cm,
        config,
        process if msg.debug_report else None,
        cache_id=cache_id,
        request_id=msg.request_id,
        feedback=feedback,
    )


def handle_api_request(
    conn: _m.Connection,
    msg: _m.ApiRequestMsg,
    server: QgsServer,
    cm: CacheManager,
    config: QgisConfig,
    process: Optional[psutil.Process],
    *,
    cache_id: str = "",
    feedback: QgsFeedback,
):
    """ Handle api request
    """
    try:
        method = _to_qgis_method(msg.method)
    except ValueError:
        _m.send_reply(conn, "HTTP Method not supported", 405)
        return

    if msg.debug_report and not process:
        _m.send_reply(conn, "No report available", 409)
        return

    assert_precondition(msg.headers is not None, "Headers are None")
    headers = msg.headers

    # Rebuild URL for Qgis server
    if msg.delegate:
        # Delegate URL
        url = f"{msg.url.removesuffix('/')}{ROOT_DELEGATE}/{msg.path.removeprefix('/')}"
        # Pass api name as header
        # to api delegate
        headers['x-qgis-api'] = msg.name
    else:
        url = msg.url
        if msg.path:
            url = f"{url.removesuffix('/')}/{msg.path.removeprefix('/')}"

    if msg.options:
        url += f"?{msg.options}"

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
        process if msg.debug_report else None,
        cache_id=cache_id,
        request_id=msg.request_id,
        feedback=feedback,
    )


def _handle_generic_request(
    url: str,
    target: Optional[str],
    allow_direct: bool,
    data: Optional[bytes],
    method: QgsServerRequest.Method,
    headers: Dict[str, str],
    conn: _m.Connection,
    server: QgsServer,
    cm: CacheManager,
    config: QgisConfig,
    process: Optional[psutil.Process],
    *,
    cache_id: str,
    request_id: Optional[str],
    feedback: QgsFeedback,
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

        entry.hit_me()

        resp_hdrs = {
            'Last-Modified': to_rfc822(entry.last_modified),
            'X-Qgis-Cache': 'MISS' if co_status in (Co.NEW, Co.UPDATED) else 'HIT',
        }

        if request_id:
            resp_hdrs['X-Request-ID'] = request_id

        project = entry.project
        response = Response(
            conn,
            co_status.value,
            headers=resp_hdrs,
            chunk_size=config.max_chunk_size,
            process=process,
            cache_id=cache_id,
            feedback=feedback,
        )
        # See https://github.com/qgis/QGIS/pull/9773
        server.serverInterface().setConfigFilePath(project.fileName())
    else:
        project = None
        response = Response(
            conn,
            process=process,
            cache_id=cache_id,
            chunk_size=config.max_chunk_size,
            feedback=feedback,
        )

    request = Request(url, method, headers, data=data)  # type: ignore
    server.handleRequest(request, response, project=project)


def request_project_from_cache(
    conn: _m.Connection,
    cm: CacheManager,
    config: QgisConfig,
    target: str,
    allow_direct: bool,
) -> Tuple[CheckoutStatus, Optional[CacheEntry]]:
    """ Handle project retrieval from cache
    """
    try:
        entry: Optional[CacheEntry]
        url = cm.resolve_path(target, allow_direct)
        md, co_status = cm.checkout(url)
        match co_status:
            case Co.NEEDUPDATE:
                # This is configuration dependent
                # Projects are updated on request only
                # if the configuration allow it
                # This is not a good idea to keep an outdated
                # project in cache since the associated resources
                # may have changed. But in the other hand it could
                # prevents access while project's ressource are
                # not fully updated
                entry = cast(CacheEntry, md)
                if config.reload_outdated_project_on_request:
                    entry, co_status = cm.update(entry.md, co_status)
            # checkout() never return UPDATED but for
            # the sake of exhaustiveness
            case Co.UNCHANGED | Co.UPDATED:
                entry = cast(CacheEntry, md)
            case Co.NEW:
                if config.load_project_on_request:
                    if config.max_projects <= len(cm):
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            target,
                        )
                        _m.send_reply(conn, "Max object reached on server", 409)
                    else:
                        entry, co_status = cm.update(cast(ProjectMetadata, md), co_status)
                else:
                    logger.error("load_project_on_request disabled for '%s'", md.uri)  # type: ignore
                    _m.send_reply(conn, target, 404)
            case Co.REMOVED:
                # Do not serve a removed project
                # Since layer's data may not exists
                # anymore
                entry = cast(CacheEntry, md)
                logger.warning("Requested removed project: %s", entry.md.uri)  # type: ignore
                _m.send_reply(conn, target, 410)
            case Co.NOTFOUND:
                entry = None
                logger.error("Requested project not found: %s", urlunsplit(url))
                _m.send_reply(conn, target, 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)
    except CacheManager.StrictCheckingFailure as err:
        _m.send_reply(conn, str(err), 422)

    return co_status, entry
