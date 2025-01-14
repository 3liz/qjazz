""" Implement Qgis server worker
    as a sub process
"""
import json
import os
import signal
import traceback

from time import sleep, time
from typing import List, Optional, Protocol, assert_never, cast

import psutil

from pydantic import JsonValue

from qgis.core import QgsFeedback
from qgis.server import QgsServer

from qjazz_cache.prelude import CacheManager, CheckoutStatus, ProjectMetadata
from qjazz_contrib.core import logger
from qjazz_contrib.core.config import ConfigProxy
from qjazz_contrib.core.qgis import (
    PluginType,
    QgisPluginService,
    init_qgis_server,
    show_all_versions,
    show_qgis_settings,
)

from . import _op_cache, _op_plugins, _op_requests
from . import messages as _m
from .config import QgisConfig
from .delegate import ApiDelegate

Co = CheckoutStatus


def load_default_project(cm: CacheManager):
    """ Load default project
    """
    default_project = os.getenv("QGIS_PROJECT_FILE")
    if default_project:
        url = cm.resolve_path(default_project, allow_direct=True)
        md, status = cm.checkout(url)
        if status == Co.NEW:
            cm.update(cast(ProjectMetadata, md), status)
        else:
            logger.error("The project %s does not exists", url)


def setup_server(conf: QgisConfig) -> QgsServer:
    """ Setup Qgis server and plugins
    """
    # Enable qgis server debug verbosity
    if logger.is_enabled_for(logger.LogLevel.DEBUG):
        os.environ['QGIS_SERVER_LOG_LEVEL'] = '0'
        os.environ['QGIS_DEBUG'] = '1'

    projects = conf.projects
    if projects.trust_layer_metadata:
        os.environ['QGIS_SERVER_TRUST_LAYER_METADATA'] = 'yes'
    if projects.disable_getprint:
        os.environ['QGIS_SERVER_DISABLE_GETPRINT'] = 'yes'

    # Disable any cache strategy
    os.environ['QGIS_SERVER_PROJECT_CACHE_STRATEGY'] = 'off'

    server = init_qgis_server(settings=conf.qgis_settings)

    CacheManager.initialize_handlers(projects)

    if logger.is_enabled_for(logger.LogLevel.DEBUG):
        print(show_qgis_settings(), flush=True)  # noqa T201

    return server


def worker_env() -> JsonValue:
    from qgis.core import Qgis
    return dict(
        qgis_version=Qgis.QGIS_VERSION_INT,
        qgis_release=Qgis.QGIS_RELEASE_NAME,
        versions=list(show_all_versions()),
        environment=dict(os.environ),
    )


class Feedback:
    def __init__(self) -> None:
        self._feedback: Optional[QgsFeedback] = None

    def cancel(self, *args) -> None:
        if self._feedback:
            self._feedback.cancel()

    def reset(self) -> None:
        self._feedback = None

    @property
    def feedback(self) -> QgsFeedback:
        if not self._feedback:
            self._feedback = QgsFeedback()
        return self._feedback


#
#  Rendez vous
#

class RendezVous(Protocol):
    def busy(self): ...
    def done(self): ...


#
# Run Qgis server
#

def qgis_server_run(
    server: QgsServer,
    conn: _m.Connection,
    conf: QgisConfig,
    rendez_vous: RendezVous,
    name: str = "",
    projects: Optional[List[str]] = None,
    reporting: bool = True,
):
    """ Run Qgis server and process incoming requests
    """
    cm = CacheManager(conf.projects, server)

    # Register the cache manager as a service
    cm.register_as_service()

    server_iface = server.serverInterface()

    # Load plugins
    plugin_s = QgisPluginService(conf.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server_iface)

    # Register as a service
    plugin_s.register_as_service()

    # Register delegation api
    api_delegate = ApiDelegate(server_iface)
    server_iface.serviceRegistry().registerApi(api_delegate)

    load_default_project(cm)

    # For reporting
    process = psutil.Process() if reporting else None

    feedback = Feedback()

    def on_sighup(*args, **kwargs):
        logger.warning("SIGHUP received, cancelling...")
        conn.cancel()
        feedback.cancel()

    signal.signal(signal.SIGHUP, on_sighup)

    while True:
        logger.trace("%s: Waiting for messages", name)
        try:
            rendez_vous.done()
            msg = None   # Prevent unbound value if recv() is interrupted
            msg = conn.recv()
            rendez_vous.busy()
            logger.debug("Received message: %s", msg.msg_id.name)
            logger.trace(">>> %s: %s", msg.msg_id.name, msg.__dict__)
            t_start = time()
            match msg:
                # --------------------
                # Qgis server Requests
                # --------------------
                case _m.OwsRequestMsg():
                    _op_requests.handle_ows_request(
                        conn,
                        msg,
                        server,
                        cm,
                        conf,
                        process,
                        cache_id=name,
                        feedback=feedback.feedback,
                    )
                case _m.ApiRequestMsg():
                    _op_requests.handle_api_request(
                        conn,
                        msg,
                        server,
                        cm,
                        conf,
                        process,
                        cache_id=name,
                        feedback=feedback.feedback,
                    )
                # --------------------
                # Global management
                # --------------------
                case _m.PingMsg():
                    _m.send_reply(conn, msg.echo)
                case _m.QuitMsg():
                    _m.send_reply(conn, None)
                    msg = None
                    break
                # --------------------
                # Cache management
                # --------------------
                case _m.CheckoutProjectMsg():
                    _op_cache.checkout_project(conn, cm, conf, msg.uri, msg.pull, cache_id=name)
                case _m.DropProjectMsg():
                    _op_cache.drop_project(conn, cm, msg.uri, name)
                case _m.ClearCacheMsg():
                    cm.clear()
                    _m.send_reply(conn, None)
                case _m.ListCacheMsg():
                    _op_cache.send_cache_list(conn, cm, cache_id=name)
                case _m.UpdateCacheMsg():
                    # We need to consume the iterator
                    # for updating the whole cache
                    for item in cm.update_cache():
                        pass
                    _m.send_reply(conn, None)
                case _m.GetProjectInfoMsg():
                    _op_cache.send_project_info(conn, cm, msg.uri, cache_id=name)
                case _m.CatalogMsg():
                    _op_cache.send_catalog(conn, cm, msg.location)
                # --------------------
                # Plugin inspection
                # --------------------
                case _m.PluginsMsg():
                    _op_plugins.inspect_plugins(conn, plugin_s)
                # --------------------
                # Config
                # --------------------
                case _m.PutConfigMsg():
                    if isinstance(conf, ConfigProxy):
                        if isinstance(msg.config, str):
                            config_data = json.loads(msg.config)
                        else:
                            config_data = msg.config
                        confservice = conf.service
                        confservice.update_config(config_data)
                        # Update log level
                        logger.set_log_level(confservice.conf.logging.level)
                        _m.send_reply(conn, None)
                    else:
                        # It does no make sense to update configuration
                        # If the configuration is not a proxy
                        # since cache manager and others will hold immutable
                        # instance of configuration
                        _m.send_reply(conn, "", 403)
                case _m.GetConfigMsg():
                    _m.send_reply(conn, conf.model_dump(mode='json'))
                # --------------------
                # Status
                # --------------------
                case _m.GetEnvMsg():
                    _m.send_reply(conn, worker_env())
                # --------------------
                # Test
                # --------------------
                case _m.SleepMsg():
                    do_sleep(conn, msg, feedback.feedback)
                # --------------------
                case _ as unreachable:
                    assert_never(unreachable)
        except KeyboardInterrupt:
            if conf.ignore_interrupt_signal:
                logger.trace("Ignoring interrupt signal")
            else:
                logger.warning("Worker interrupted")
                break
        except Exception as exc:
            if msg:
                logger.critical(traceback.format_exc())
                _m.send_reply(conn, str(exc), 500)
            else:
                # No message has been set !
                # Exception occured outside message handling
                raise
        finally:
            if msg and not conn.cancelled:
                if logger.is_enabled_for(logger.LogLevel.TRACE):
                    logger.trace(
                        "%s\t%s\tResponse time: %d ms",
                        name,
                        msg.msg_id.name,
                        int((time() - t_start) * 1000.),
                    )
            # Reset feedback
            feedback.reset()

    logger.debug("Worker exiting")


def do_sleep(conn: _m.Connection, msg: _m.SleepMsg, feedback: QgsFeedback):
    """ Feedback test
    """
    done_ts = time() + msg.delay
    canceled = False
    logger.info("Entering sleep mode for %s seconds", msg.delay)
    while done_ts > time():
        sleep(1.0)
        canceled = feedback.isCanceled()
        #if canceled:
        #    logger.info("** Sleep cancelled **")
        #    break
    if not canceled:
        logger.info("** Worker is now awake  **")
        _m.send_nodata(conn)
