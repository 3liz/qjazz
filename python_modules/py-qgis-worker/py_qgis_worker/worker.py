""" Implement Qgis server worker
    as a sub process
"""
import os
import traceback

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
    CatalogEntry,
    CheckoutStatus,
)

from . import messages as _m
from .config import WorkerConfig
from .requests import Request, Response

Co = CheckoutStatus


def load_default_project(cm: CacheManager):
    """ Load default project
    """
    default_project = os.getenv("QGIS_PROJECT_FILE")
    if default_project:
        url = cm.resolve_path(default_project, allow_direct=True)
        md, status = cm.checkout(url)
        match status:
            case Co.NEW:
                cm.update(md, status)
            case _:
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
    cm = CacheManager(config.projects)

    # Load plugins
    plugin_s = QgisPluginService(config.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server.serverInterface())

    load_default_project(cm)

    # For reporting
    _process = psutil.Process() if psutil else None

    while True:
        msg = conn.recv()
        try:
            match msg.msg_id:
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
                case _m.MsgType.PING:
                    _m.send_reply(conn, None)
                case _m.MsgType.QUIT:
                    _m.send_reply(conn, None)
                    break
                case _m.MsgType.PULL_PROJECT:
                    _m.send_reply(conn, pull_project(cm, msg.uri))
                case _m.MsgType.UNLOAD_PROJECT:
                    _m.send_reply(conn, unload_project(cm, msg.uri))
                case _m.MsgType.CLEAR_CACHE:
                    cm.clear()
                    _m.send_reply(conn, None)
                case _m.MsgType.LIST_CACHE:
                    _m.send_reply(conn, list_cache(cm, msg.status))
                case _m.MsgType.PROJECT_INFO:
                    _m.send_reply(conn, None, 405)
                case _m.MsgType.LIST_PLUGINS:
                    _m.send_reply(conn, None, 405)
                case _ as unreachable:
                    assert_never(unreachable)
        except Exception as exc:
            logger.critical(traceback.format_exc())
            _m.send_reply(conn, str(exc), 500)

#
# Server Request
#


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
    # Rebuild URL for Qgis server
    url = msg.url + f"?SERVICE={msg.service}&REQUEST={msg.request}"
    if msg.options:
        url += '&'
        url += '&'.join(f"{k}={v}" for k, v in msg.options.items())

    _handle_generic_request(
        url,
        msg.target,
        msg.direct,
        None,
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
    _handle_generic_request(
        msg.url,
        msg.target,
        msg.direct,
        msg.data,
        msg.headers,
        conn,
        server,
        cm,
        config,
        _process
    )


def _handle_generic_request(
    url: str,
    target: str,
    allow_direct: str,
    data: Optional[bytes],
    headers: Dict[str, str],
    conn: Connection,
    server: QgsServer,
    cm: CacheManager,
    config: WorkerConfig,
    _process: Optional,
):
    """ Handle generic Qgis request
    """
    co_status, entry = request_project_from_cache(
        conn,
        cm,
        config,
        target=target,
        allow_direct=allow_direct,
    )

    if co_status in (Co.UPDATED, Co.REMOVED):
        # Cleanup cached files
        server.serverInterface().removeConfigCacheEntry(
            entry.project.fileName()
        )

    if entry and co_status != Co.REMOVED:
        project = entry.project
        request = Request(
            url,
            QgsServerRequest.GetMethod,
            headers,
            data=data,
        )
        response = Response(
            conn,
            co_status,
            last_modified=entry.last_modified,
            _process=_process,
        )

        # See https://github.com/qgis/QGIS/pull/9773
        server.serverInterface().setConfigFilePath(project.fileName())
        server.handleRequest(request, response, project=project)

    return co_status


def request_project_from_cache(
    conn: Connection,
    cm: CacheManager,
    config: WorkerConfig,
    target: str,
    allow_direct: bool,
) -> Tuple[CheckoutStatus, Optional[CatalogEntry]]:
    """ Handle project retrieval from cache
    """
    try:
        entry = None
        target = cm.resolve_path(target, allow_direct)
        md, co_status = cm.checkout(target)
        match co_status:
            case Co.NEEDUPDATE:
                if config.reload_outdated_project_on_request:
                    entry = cm.update(md, co_status)
                    co_status = Co.UPDATED
                else:
                    entry = md
            case Co.UNCHANGED:
                entry = md
            case Co.NEW:
                if config.load_project_on_request:
                    if config.max_projects <= cm.size:
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            target,
                        )
                        _m.send_reply(conn, None, 403)
                    else:
                        entry = cm.update(md, co_status)
                else:
                    logger.error("Request for loading NEW project '%s'", target)
                    _m.send_reply(conn, None, 403)
            case Co.REMOVED:
                # Do not serve a removed project
                # Since layer's data may not exists
                # anymore
                _m.send_reply(conn, None, 410)
                entry = md
            case Co.NOTFOUND:
                _m.send_reply(conn, None, 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed:
        _m.send_reply(conn, None, 403)

    return co_status, entry

#
# Commandes
#


def list_cache(
    cm: CacheManager,
    status: Optional[CheckoutStatus]
) -> _m.ListCache:
    """ List cached items
    """
    co = (cm.checkout(e) for e in cm.iter())
    if status is not None:
        co = filter(lambda n: n[1] == status, co)
    return [
        _m.CacheInfo(
            e.md.uri,
            last_modified=e.md.last_modified,
            saved_version=e.project.lastSaveVersion().text(),
            status=status,
        ) for (e, status) in co
    ]


def unload_project(cm: CacheManager, uri: str) -> _m.CacheInfo:
    """ Unload a project from cache
    """
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True)
    )

    match status:
        case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
            e = cm.update(md, Co.REMOVED)
            return _m.CacheInfo(
                url=md.uri,
                last_modified=md.last_modified,
                saved_version=e.project.lastSaveVersion().text(),
                status=status,
            )
        case _:
            return _m.CacheInfo(
                url=md.uri,
                status=status,
            )


def pull_project(cm: CacheManager, uri: str) -> _m.CacheInfo:
    """ Load a project into cache

        Returns the cache info
    """
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True)
    )

    match status:
        case Co.NEW | Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
            e = cm.update(md, status)
            return _m.CacheInfo(
                url=md.uri,
                last_modified=md.last_modified,
                saved_version=e.project.lastSaveVersion().text(),
                status=status,
            )
        case Co.NOTFOUND:
            return _m.CacheInfo(
                url=md.uri,
                status=status,
            )
        case _ as unreachable:
            assert_never(unreachable)
