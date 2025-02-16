#
# Child process for testing
#
import sys
import os
import signal
import traceback

from contextlib import closing
from datetime import datetime

from qjazz_contrib.core import logger
from qjazz_contrib.core.utils import to_iso8601
from qjazz_cache.status import CheckoutStatus
from qjazz_ogc import OgcEndpoints
from qjazz_rpc.connection import Connection, RendezVous
from qjazz_rpc import messages as m_
from time import sleep, time;


def echo(*args):
    print(*args, flush=True, file=sys.stderr)


PROJECTS: dict[m_.CacheInfo] = {}

last_modified = to_iso8601(datetime.fromtimestamp(time()))


def cache_info(uri, status):
    timestamp = time()
    return m_.CacheInfo(
        uri=uri,
        status=status.value,
        in_cache=False,
        cache_id="test",
        timestamp=int(timestamp),
        name=uri,
        storage="test",
        last_modified=last_modified,
        saved_version="Test1.0",
        debug_metadata={},
        last_hit=int(timestamp),
        hits=0,
        pinned=True,
    )
   

def new_project(uri):
    info = cache_info(uri, CheckoutStatus.NEW)
    info.in_cache = True
    PROJECTS[uri] = info
    return info


def get_project(uri: str, pull: bool):
    info = PROJECTS.get(uri)
    if not info:
        if pull: 
            info = new_project(uri)
        else:
            info = cache_info(uri, CheckoutStatus.NEW)
    else:
        info.status = CheckoutStatus.UNCHANGED.value
    return info


def drop_project(uri: str):
    info = PROJECTS.get(uri)
    if not info: 
        info = new_project(uri)
    else:
        info.status = CheckoutStatus.REMOVED.value
        del PROJECTS[uri]
    return info


def catalog_item(name: str) -> m_.CatalogItem:
    return m_.CatalogItem(
        uri="/france/france_parts",
        name=name,
        storage="file",
        last_modified=to_iso8601(datetime.fromtimestamp(time())), 
        public_uri="/france/france_parts",
    )


def project_info(uri: str) -> m_.ProjectInfo:
    return m_.ProjectInfo(
        status=CheckoutStatus.UNCHANGED.value,
        uri=uri,
        filename="/path/to/file",
        crs="EPSG:4326",
        last_modified=to_iso8601(datetime.fromtimestamp(time())),
        storage="file",
        has_bad_layers=False,
        layers=[
            m_.LayerInfo(
                layer_id="1234",
                name="Layer",
                source="whatever",
                crs="EPSG:4326",
                is_valid=True,
                is_spatial=True,
            )
        ],
        cache_id="Test",
    )


def plugin_item(name: str) -> m_.PluginInfo:
    return m_.PluginInfo(
        name=name,
        path="/path/to/plugin",
        plugin_type="test",
        metadata= dict(
            version=1,
        ),
    )


def run(name: str, projects: list[str]) -> None:

    #echo("RENDEZ_VOUS is", os.getenv("RENDEZ_VOUS"))
    rendez_vous = RendezVous()

    # Display configuration
    log_level = os.getenv("CONF_LOGGING__LEVEL", "<notset>")
    config = os.getenv("CONF_QGIS", "<notset>")
    
    logger.setup_log_handler(logger.LogLevel[log_level.upper()])

    logger.debug("== Log level set to: %s", log_level)
    logger.debug("== Config: %s", config)

    def handle_sigterm(*args, **kwargs):
        logger.debug("Caught SIGTERM")
        raise SystemExit(1)
    
    signal.signal(signal.SIGTERM, handle_sigterm) 
    signal.signal(signal.SIGHUP, lambda *args: logger.debug("Caught SIGHUP")) 

    logger.debug("== Projects %s", projects)

    with closing(Connection()) as conn:
        while True:
            try:
                rendez_vous.done()
                logger.debug(f"{name}: waiting for messages")
                msg = None # Prevent unbound value if recv() is interrupted
                msg = conn.recv()
                logger.debug("Received message %s", msg.msg_id.name)
                # Notify as busy
                rendez_vous.busy()
                logger.debug(f">>> {msg.msg_id.name}, {msg.__dict__}")
                match msg:
                    case m_.PingMsg():
                        m_.send_reply(conn, msg.echo)
                    case m_.QuitMsg():
                        m_.send_reply(conn, None)
                        break
                    case m_.SleepMsg():
                        logger.info("Entering sleep made for %s seconds", msg.delay)
                        sleep(msg.delay)
                        logger.info("Worker is now awake")
                        m_.send_nodata(conn)
                    case m_.OwsRequestMsg():
                        prefix = msg.header_prefix or ""
                        m_.send_reply(
                            conn,
                            m_.RequestReply(
                                status_code=200,
                                headers=[(f"{prefix}content-type", "application/test")],
                                checkout_status=CheckoutStatus.NEW.value,
                            ),
                        )
                        # Send chunks
                        m_.send_chunk(conn, b"chunk1")
                        m_.send_chunk(conn, b"chunk2")
                        m_.send_chunk(conn, b"")
                    case m_.ApiRequestMsg():
                        prefix = msg.header_prefix or ""
                        m_.send_reply(
                            conn,
                            m_.RequestReply(
                                status_code=200,
                                headers=[(f"{prefix}content-type", "application/test")],
                                checkout_status=CheckoutStatus.NEW.value,
                            ),
                        )
                        m_.send_chunk(conn, b"<data>")
                        m_.send_chunk(conn, b"")
                    case m_.CollectionsMsg():
                        m_.send_reply(
                            conn,
                            m_.CollectionsPage(
                                schema="",
                                next=False,
                                items=[
                                    m_.CollectionsItem(
                                        name="Test000",
                                        json="",
                                        endpoints=(
                                            OgcEndpoints.MAP|OgcEndpoints.FEATURES
                                        ).value,
                                    ),
                                ],
                            )
                        )
                    case m_.GetEnvMsg():
                        m_.send_reply(conn, dict(
                            qgis_version=0,
                            qgis_release="n/a",
                            versions="n/a",
                            environment=dict(os.environ),
                        ))
                    case m_.CheckoutProjectMsg():
                        m_.send_reply(conn, get_project(msg.uri, msg.pull))
                    case m_.UpdateCacheMsg():
                        m_.send_reply(conn, None)
                    case m_.ListCacheMsg():
                        m_.stream_data(conn, (v for v in PROJECTS.values()))
                    case m_.DropProjectMsg():
                        m_.send_reply(conn, drop_project(msg.uri))
                    case m_.ClearCacheMsg():
                        m_.send_reply(conn, None)
                    case m_.CatalogMsg():
                        m_.stream_data(
                            conn,
                            (
                                catalog_item("cat_1"),
                                catalog_item("cat_2"),
                            )
                        )
                    case m_.GetProjectInfoMsg():
                        m_.send_reply(conn, project_info(msg.uri))
                    case m_.PluginsMsg():
                        m_.stream_data(
                            conn,
                            (
                                plugin_item("plugin_1"),
                                plugin_item("plugin_2"),
                            ),
                        )
                    case _: 
                        raise ValueError("Unhandled message")
            except KeyboardInterrupt:
                logger.warning("Ignoring interrupt signal")
            except Exception as exc:
                traceback.print_exc()
                if msg:
                    m_.send_reply(conn, str(exc), 500)
                else:
                    raise
            except SystemExit as exc:
                raise
        logger.debug("Child process Terminated")


if __name__ == '__main__':
    import sys
    name = sys.argv[1]
    projects = sys.argv[2:]
    run(name, projects)

