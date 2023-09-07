""" Implement Qgis server worker
    as a sub process
"""
import os
import traceback

from urllib.parse import urlunsplit

try:
    import psutil
except ImportError:
    psutil = None

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
from py_qgis_contrib.core.qgis import (
    init_qgis_server,
    show_qgis_settings,
    PluginType,
    QgisPluginService,
)
from py_qgis_project_cache import (
    CacheManager,
    CacheEntry,
    CheckoutStatus,
)

from . import messages as _m
from .config import WorkerConfig
from .requests import Request, Response, _to_qgis_method
from .plugins import inspect_plugins

Co = CheckoutStatus


def load_default_project(cm: CacheManager):
    """ Load default project
    """
    default_project = os.getenv("QGIS_PROJECT_FILE")
    if default_project:
        url = cm.resolve_path(default_project, allow_direct=True)
        md, status = cm.checkout(url)
        if status == Co.NEW:
            cm.update(md, status)
        else:
            logger.error("The project %s does not exists", url)


def setup_server(config: WorkerConfig) -> QgsServer:
    """ Setup Qgis server and plugins
    """
    # Enable qgis server debug verbosity
    if logger.isEnabledFor(logger.LogLevel.DEBUG):
        os.environ['QGIS_SERVER_LOG_LEVEL'] = '0'
        os.environ['QGIS_DEBUG'] = '1'

    projects = config.projects
    if projects.trust_layer_metadata:
        os.environ['QGIS_SERVER_TRUST_LAYER_METADATA'] = 'yes'
    if projects.disable_getprint:
        os.environ['QGIS_SERVER_DISABLE_GETPRINT'] = 'yes'

    # Disable any cache strategy
    os.environ['QGIS_SERVER_PROJECT_CACHE_STRATEGY'] = 'off'

    server = init_qgis_server()
    CacheManager.initialize_handlers()

    print(show_qgis_settings())

    return server


#
# Run Qgis server
#
def qgis_server_run(server: QgsServer, conn: Connection, config: WorkerConfig):
    """ Run Qgis server and process incoming requests
    """
    cm = CacheManager(config.projects, server)

    # Load plugins
    plugin_s = QgisPluginService(config.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server.serverInterface())

    load_default_project(cm)

    # For reporting
    _process = psutil.Process() if psutil else None

    while True:
        logger.debug("Waiting for messages")
        msg = conn.recv()
        logger.debug("Received message: %s", msg.msg_id.name)
        try:
            match msg.msg_id:
                # --------------------
                # Qgis server Requests
                # --------------------
                case _m.MsgType.OWSREQUEST:
                    handle_ows_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process
                    )
                case _m.MsgType.REQUEST:
                    handle_generic_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process
                    )
                # --------------------
                # Global management
                # --------------------
                case _m.MsgType.PING:
                    _m.send_reply(conn, None)
                case _m.MsgType.QUIT:
                    _m.send_reply(conn, None)
                    break
                # --------------------
                # Cache managment
                # --------------------
                case _m.MsgType.CHECKOUT_PROJECT:
                    _m.send_reply(
                        conn,
                        checkout_project(cm, msg.uri, msg.pull)
                    )
                case _m.MsgType.DROP_PROJECT:
                    _m.send_reply(
                        conn,
                        drop_project(cm, msg.uri)
                    )
                case _m.MsgType.CLEAR_CACHE:
                    cm.clear()
                    _m.send_reply(conn, None)
                case _m.MsgType.LIST_CACHE:
                    send_cache_list(conn, cm, msg.status_filter)
                case _m.MsgType.PROJECT_INFO:
                    _m.send_reply(conn, None, 405)
                # --------------------
                # Plugin inspection
                # --------------------
                case _m.MsgType.PLUGINS:
                    inspect_plugins(conn, plugin_s)
                # --------------------
                case _ as unreachable:
                    assert_never(unreachable)
        except Exception as exc:
            logger.critical(traceback.format_exc())
            _m.send_reply(conn, str(exc), 500)


#
# Server Request
#
QGIS_MISSING_PROJECT_ERROR_MSG = "No project defined"


def handle_ows_request(
    conn: Connection,
    msg: _m.OWSRequest,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
):
    """ Handle OWS request
    """
    if not msg.target:
        exception = QgsServerException(QGIS_MISSING_PROJECT_ERROR_MSG, 400)
        response = Response(conn)
        response.write(exception)
        response.finish()
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
        _process
    )


def handle_generic_request(
    conn: Connection,
    msg: _m.Request,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
):
    try:
        method = _to_qgis_method(msg.method)
    except ValueError:
        _m.send_reply(conn, "HTTP Method not supported", 405)
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
        _process
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
            _process=_process,
        )
        # See https://github.com/qgis/QGIS/pull/9773
        server.serverInterface().setConfigFilePath(project.fileName())
    else:
        project = None
        response = Response(conn, _process=_process)

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
    except CacheManager.ResourceNotAllowed:
        _m.send_reply(conn, None, 403)

    return co_status, entry

#
# Commandes
#


def drop_project(cm: CacheManager, uri: str) -> _m.CacheInfo:
    """ Unload a project from cache
    """
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True)
    )

    match status:
        case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
            e, status = cm.update(md, Co.REMOVED)
            return _m.CacheInfo(
                uri=md.uri,
                in_cache=False,
                last_modified=md.last_modified,
                saved_version=e.project.lastSaveVersion().text(),
                status=status,
            )
        case _:
            return _m.CacheInfo(
                uri=md.uri,
                in_cache=False,
                status=status,
            )


# Helper for returning CacheInfo from
# cache entry
def _cache_info_from_entry(e: CacheEntry, status, in_cache=True) -> _m.CacheInfo:
    return _m.CacheInfo(
        uri=e.uri,
        in_cache=in_cache,
        status=status,
        name=e.name,
        storage=e.storage,
        last_modified=e.last_modified,
        saved_version=e.project.lastSaveVersion().text(),
        debug_metadata=e.debug_meta.__dict__.copy(),
    )


def checkout_project(
    cm: CacheManager,
    uri: str,
    pull: bool,
) -> _m.CacheInfo:
    """ Load a project into cache

        Returns the cache info
    """
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True)
    )

    if not pull:
        match status:
            case Co.NEW:
                return _m.CacheInfo(
                    uri=md.uri,
                    in_cache=False,
                    status=status,
                    storage=md.storage,
                    last_modified=md.last_modified
                )
            case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
                return _cache_info_from_entry(md, status)
            case Co.NOTFOUND:
                return _m.CacheInfo(
                    uri=md.uri,
                    in_cache=False,
                    status=status,
                )
            case _ as unreachable:
                assert_never(unreachable)
    else:
        match status:
            case Co.NEW:
                e, status = cm.update(md, status)
                return _cache_info_from_entry(e, status)
            case Co.NEEDUPDATE | Co.REMOVED:
                e, status = cm.update(md, status)
                return _cache_info_from_entry(e, status, status != Co.REMOVED)
            case Co.UNCHANGED:
                return _cache_info_from_entry(md, status)
            case Co.NOTFOUND:
                return _m.CacheInfo(
                    uri=md.uri,
                    in_cache=False,
                    status=status,
                )
            case _ as unreachable:
                assert_never(unreachable)


#
# Send cache list
#
def send_cache_list(
    conn: Connection,
    cm: CacheManager,
    status_filter: Optional[CheckoutStatus],
):
    co = cm.checkout_iter()
    if status_filter:
        co = filter(lambda n: n[1] == status_filter, co)

    count = len(cm)
    _m.send_reply(conn, count)
    if count:
        try:
            # Stream CacheInfo
            for entry, status in co:
                _m.send_reply(conn, _cache_info_from_entry(entry, status), 206)
        except Exception:
            logger.error("Aborting stream")
            raise
        else:
            # EOT
            _m.send_reply(conn, None)
