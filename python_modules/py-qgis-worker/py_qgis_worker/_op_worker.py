""" Implement Qgis server worker
    as a sub process
"""
import os
import traceback

from time import time

try:
    import psutil
except ImportError:
    psutil = None

from typing_extensions import (
    Dict,
    assert_never,
)
from multiprocessing.connection import Connection

from qgis.server import QgsServer

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigProxy
from py_qgis_contrib.core.qgis import (
    init_qgis_server,
    show_qgis_settings,
    show_all_versions,
    PluginType,
    QgisPluginService,
)
from py_qgis_cache import (
    CacheManager,
    CheckoutStatus,
)

from .config import WorkerConfig
from .serverapi import ApiDelegate

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


def worker_env() -> Dict:
    from qgis.core import Qgis
    return dict(
        qgis_version=Qgis.QGIS_VERSION_INT,
        qgis_release=Qgis.QGIS_RELEASE_NAME,
        versions=list(show_all_versions()),
        environment=dict(os.environ),
    )

#
# Run Qgis server
#


def qgis_server_run(
        server: QgsServer,
        conn: Connection,
        config: WorkerConfig,
        event,
        name: str = "",
):
    """ Run Qgis server and process incoming requests
    """
    cm = CacheManager(config.projects, server)

    server_iface = server.serverInterface()

    # Load plugins
    plugin_s = QgisPluginService(config.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server_iface)

    # Register delegation api
    api_delegate = ApiDelegate(server_iface)
    server_iface.serviceRegistry().registerApi(api_delegate)

    load_default_project(cm)

    # For reporting
    _process = psutil.Process() if psutil else None

    event.set()
    while True:
        logger.trace("%s: Waiting for messages", name)
        try:
            msg = conn.recv()
            event.clear()
            logger.debug("Received message: %s", msg.msg_id.name)
            logger.trace(">>> %s: %s", msg.msg_id.name, msg.__dict__)
            _t_start = time()
            match msg.msg_id:
                # --------------------
                # Qgis server Requests
                # --------------------
                case _m.MsgType.OWSREQUEST:
                    _op_requests.handle_ows_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process, cache_id=name,
                    )
                case _m.MsgType.APIREQUEST:
                    _op_requests.handle_api_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process, cache_id=name,
                    )
                case _m.MsgType.REQUEST:
                    _op_requests.handle_generic_request(
                        conn,
                        msg,
                        server,
                        cm, config, _process, cache_id=name,
                    )
                # --------------------
                # Global management
                # --------------------
                case _m.MsgType.PING:
                    _m.send_reply(conn, msg.echo)
                case _m.MsgType.QUIT:
                    _m.send_reply(conn, None)
                    break
                # --------------------
                # Cache managment
                # --------------------
                case _m.MsgType.CHECKOUT_PROJECT:
                    _op_cache.checkout_project(conn, cm, msg.uri, msg.pull, cache_id=name)
                case _m.MsgType.DROP_PROJECT:
                    _op_cache.drop_project(conn, cm, msg.uri, name)
                case _m.MsgType.CLEAR_CACHE:
                    cm.clear()
                    _m.send_reply(conn, None)
                case _m.MsgType.LIST_CACHE:
                    _op_cache.send_cache_list(conn, cm, msg.status_filter, cache_id=name)
                case _m.MsgType.UPDATE_CACHE:
                    _op_cache.update_cache(conn, cm, cache_id=name)
                case _m.MsgType.PROJECT_INFO:
                    _op_cache.send_project_info(conn, cm, msg.uri, cache_id=name)
                case _m.MsgType.CATALOG:
                    _op_cache.send_catalog(conn, cm, msg.location)
                # --------------------
                # Plugin inspection
                # --------------------
                case _m.MsgType.PLUGINS:
                    _op_plugins.inspect_plugins(conn, plugin_s)
                # --------------------
                # Config
                # --------------------
                case _m.MsgType.PUT_CONFIG:
                    if isinstance(config, ConfigProxy):
                        config.service.update_config(msg.config)
                        # Update log level
                        logger.set_log_level()
                        _m.send_reply(conn, None)
                    else:
                        # It does no make sense to update configuration
                        # If the configuration is not a proxy
                        # since cache manager and others will hold immutable
                        # instance of configuration
                        _m.send_reply(conn, "", 403)
                case _m.MsgType.GET_CONFIG:
                    _m.send_reply(conn, config.model_dump())
                # --------------------
                # Status
                # --------------------
                case _m.MsgType.ENV:
                    _m.send_reply(conn, worker_env())
                # --------------------
                case _ as unreachable:
                    assert_never(unreachable)
        except KeyboardInterrupt:
            logger.info("Worker interrupted")
            break
        except Exception as exc:
            logger.critical(traceback.format_exc())
            _m.send_reply(conn, str(exc), 500)
        finally:
            if not event.is_set():
                _t_end = time()
                if logger.isEnabledFor(logger.LogLevel.TRACE):
                    logger.trace(
                        "%s\t%s\tResponse time: %d ms",
                        name,
                        msg.msg_id.name,
                        int((_t_end - _t_start) * 1000.),
                    )
                event.set()
