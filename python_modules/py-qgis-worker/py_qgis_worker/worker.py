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
    assert_never,
)
from multiprocessing.connection import Connection

from qgis.server import QgsServer

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.qgis import (
    init_qgis_server,
    show_qgis_settings,
    PluginType,
    QgisPluginService,
)
from py_qgis_project_cache import (
    CacheManager,
    CheckoutStatus,
)

from .config import WorkerConfig

from . import messages as _m
from . import _op_requests
from . import _op_plugins
from . import _op_cache

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
                    _op_requests.handle_ows_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process
                    )
                case _m.MsgType.REQUEST:
                    _op_requests.handle_generic_request(
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
                    _op_cache.checkout_project(conn, cm, msg.uri, msg.pull)
                case _m.MsgType.DROP_PROJECT:
                    _op_cache.drop_project(conn, cm, msg.uri)
                case _m.MsgType.CLEAR_CACHE:
                    cm.clear()
                    _m.send_reply(conn, None)
                case _m.MsgType.LIST_CACHE:
                    _op_cache.send_cache_list(conn, cm, msg.status_filter)
                case _m.MsgType.PROJECT_INFO:
                    _op_cache.send_project_info(conn, cm, msg.uri)
                case _m.MsgType.CATALOG:
                    _op_cache.send_catalog(conn, cm, msg.location)
                # --------------------
                # Plugin inspection
                # --------------------
                case _m.MsgType.PLUGINS:
                    _op_plugins.inspect_plugins(conn, plugin_s)
                # --------------------
                case _ as unreachable:
                    assert_never(unreachable)
        except Exception as exc:
            logger.critical(traceback.format_exc())
            _m.send_reply(conn, str(exc), 500)
