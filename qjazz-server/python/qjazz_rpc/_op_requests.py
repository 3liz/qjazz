#
# Qgis server request operations
#
import os

from string import capwords
from typing import Optional, assert_never, cast
from urllib.parse import urlunsplit

from qgis.core import QgsFeedback
from qgis.server import QgsServer, QgsServerRequest, QgsServerResponse

from qjazz_cache.prelude import CacheEntry, CacheManager, CheckoutStatus, ProjectMetadata
from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_precondition
from qjazz_contrib.core.utils import to_rfc822

from . import messages as _m
from ._op_cache import evict_project_from_cache
from ._op_map import InvalidMapRequest, prepare_map_request
from .config import QgisConfig
from .delegate import ROOT_DELEGATE
from .log import Log
from .requests import Request, Response, _to_qgis_method

Co = CheckoutStatus


#
# Server Request
#


def handle_ows_request(
    conn: _m.Connection,
    msg: _m.OwsRequestMsg,
    server: QgsServer,
    cm: CacheManager,
    config: QgisConfig,
    *,
    cache_id: str = "",
    feedback: QgsFeedback,
):
    """ Handle OWS request
    """

    target = msg.target
    if not target:
        target = os.getenv("QGIS_PROJECT_FILE", "")
        # OWS require a project file
        if not target:
            _m.send_reply(conn, "Missing project", 400)
            return

    log = Log()

    entry, co_status = get_project(
        conn,
        cm,
        config,
        target,
        allow_direct=msg.direct,
    )
    if not entry:
        return

    resp_hdrs: dict[str, str] | None = None

    options = msg.options
    service = msg.service
    request = msg.request

    if request == 'qjazz-request-map':
        service = "WMS"
        request = "GetMap"
        try:
            assert_precondition(options is not None)
            map_req = prepare_map_request(entry.project, cast(str, options))
            method = QgsServerRequest.GetMethod
        except InvalidMapRequest as err:
            _m.send_reply(conn, f"Invalid request: {err}", 400)
            return

        options = map_req.options
        resp_hdrs = map_req.headers

    elif msg.method:
        try:
            method = _to_qgis_method(msg.method)
        except ValueError:
            _m.send_reply(conn, "HTTP Method not supported", 405)
            return
    else:
        method = QgsServerRequest.GetMethod

    if options:
        # Rebuild URL for Qgis server
        # XXX options is the full query string
        url = f"{msg.url or ''}?{options}"
    else:
        url = f"{msg.url or ''}?SERVICE={service or 'WMS'}&REQUEST={request}"
        if msg.version:
            url += f"&VERSION={msg.version}"

    resp = _handle_generic_request(
        url,
        entry,
        co_status,
        msg.body,
        method,
        msg.headers,
        conn,
        server,
        config,
        cache_id=cache_id,
        request_id=msg.request_id,
        feedback=feedback,
        header_prefix=msg.header_prefix,
        content_type=msg.content_type,
        resp_hdrs=resp_hdrs,
    )

    log.log(
        msg.request_id or "-",
        service or "<UNKN>",
        request or "<UNKN>",
        target,
        resp,
    )


def handle_api_request(
    conn: _m.Connection,
    msg: _m.ApiRequestMsg,
    server: QgsServer,
    cm: CacheManager,
    config: QgisConfig,
    *,
    cache_id: str = "",
    feedback: QgsFeedback,
):
    """ Handle api request
    """
    target = msg.target
    if not target:
        target = os.getenv("QGIS_PROJECT_FILE", "")

    if target:
        entry, co_status = get_project(
            conn,
            cm,
            config,
            target,
            allow_direct=msg.direct,
        )
        if not entry:
            return
    else:
        entry, co_status = (None, None)

    try:
        method = _to_qgis_method(msg.method)
    except ValueError:
        _m.send_reply(conn, "HTTP Method not supported", 405)
        return

    assert_precondition(msg.headers is not None, "Headers are None")
    headers = msg.headers

    # Rebuild URL for Qgis server
    if msg.delegate:
        # Delegate URL
        url = f"{msg.url.removesuffix('/')}{ROOT_DELEGATE}/{msg.path.removeprefix('/')}"
        # Pass api name as header
        # to api delegate
        headers.append(('x-qgis-api', msg.name))
    else:
        url = msg.url
        if msg.path:
            url = f"{url.removesuffix('/')}/{msg.path.removeprefix('/')}"

    if msg.options:
        url += f"?{msg.options}"

    _handle_generic_request(
        url,
        entry,
        co_status,
        msg.data,
        method,
        msg.headers,
        conn,
        server,
        config,
        cache_id=cache_id,
        request_id=msg.request_id,
        feedback=feedback,
        header_prefix=msg.header_prefix,
        content_type=msg.content_type,
    )


def _handle_generic_request(
    url: str,
    entry: Optional[CacheEntry],
    co_status: Optional[Co],
    data: Optional[bytes],
    method: QgsServerRequest.Method,
    headers: list[tuple[str, str]],
    conn: _m.Connection,
    server: QgsServer,
    config: QgisConfig,
    *,
    cache_id: str,
    request_id: Optional[str],
    feedback: QgsFeedback,
    header_prefix: Optional[str],
    content_type: Optional[str],
    resp_hdrs: Optional[dict[str, str]] = None,
) -> QgsServerResponse:
    """ Handle generic Qgis request
    """
    if entry:
        assert_precondition(co_status is not None)
        project = entry.project
        resp_hdrs = resp_hdrs or {}
        resp_hdrs.update((
            ('x-qgis-last-modified', to_rfc822(entry.last_modified)),
            ('x-qgis-cache', 'MISS' if cast(Co, co_status) in (Co.NEW, Co.UPDATED) else 'HIT'),
        ))

        response = Response(
            conn,
            cast(Co, co_status).value,
            headers=resp_hdrs,
            chunk_size=config.max_chunk_size,
            cache_id=cache_id,
            feedback=feedback,
            header_prefix=header_prefix,
        )
        # See https://github.com/qgis/QGIS/pull/9773
        server.serverInterface().setConfigFilePath(project.fileName())
    else:
        project = None
        response = Response(
            conn,
            cache_id=cache_id,
            chunk_size=config.max_chunk_size,
            feedback=feedback,
            header_prefix=header_prefix,
        )

    # XXX QGIS does not complies to standard and handle X-Qgis-* headers
    # in case sensitive way
    req_hdrs = {capwords(k, sep='-'): v for k, v in headers if not k.startswith('grpc-')}
    if content_type:
        req_hdrs['Content-Type'] = content_type

    request = Request(url, method, req_hdrs, data=data)  # type: ignore
    server.handleRequest(request, response, project=project)
    return response


def get_project(
    conn: _m.Connection,
    cm: CacheManager,
    config: QgisConfig,
    target:  str,
    allow_direct: bool,
) -> tuple[Optional[CacheEntry], Co]:

    # XXX Prevent error in cache manager
    if not target.startswith("/"):
        target = f"/{target}"

    co_status, entry = request_project_from_cache(
        conn,
        cm,
        config,
        target=target,
        allow_direct=allow_direct,
    )

    if not entry or co_status == Co.REMOVED:
        return (None, co_status)

    entry.hit_me()

    return (entry, co_status)


def request_project_from_cache(
    conn: _m.Connection,
    cm: CacheManager,
    config: QgisConfig,
    target: str,
    allow_direct: bool,
) -> tuple[CheckoutStatus, Optional[CacheEntry]]:
    """ Handle project retrieval from cache
    """
    try:
        entry: Optional[CacheEntry] = None
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
                    if config.max_projects <= len(cm) and not evict_project_from_cache(cm):
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            target,
                        )
                        _m.send_reply(conn, "Max object reached on server", 409)
                    else:
                        entry, co_status = cm.update(cast(ProjectMetadata, md), co_status)
                else:
                    logger.error("load_project_on_request disabled for '%s'", md.uri)  # type: ignore
                    _m.send_reply(conn, f"Resource not found: {target}", 404)
            case Co.REMOVED:
                # Do not serve a removed project
                # Since layer's data may not exists
                # anymore
                entry = cast(CacheEntry, md)
                logger.warning("Requested removed project: %s", entry.md.uri)  # type: ignore
                _m.send_reply(conn, target, 410)
            case Co.NOTFOUND:
                logger.error("Requested project not found: %s", urlunsplit(url))
                _m.send_reply(conn, f"Resource not found: {target}", 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)
    except CacheManager.StrictCheckingFailure as err:
        _m.send_reply(conn, str(err), 500)

    return co_status, entry
