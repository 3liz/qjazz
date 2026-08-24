#
# Config operation
#
import json

from qjazz_core import logger
from qjazz_core.config import ConfigProxy

from . import messages as _m
from .config import QgisConfig


def put_config(
    conn: _m.Connection,
    msg: _m.PutConfigMsg,
    conf: QgisConfig,
):
    if isinstance(conf, ConfigProxy):
        logger.notice("Updating configuration")
        config_data = json.loads(msg.config) if isinstance(msg.config, str) else msg.config
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


def get_config(conn: _m.Connection, conf: QgisConfig):
    if isinstance(conf, ConfigProxy):
        confservice = conf.service
        _m.send_reply(conn, confservice.conf.model_dump(mode="json"))
    else:
        _m.send_reply(conn, conf.model_dump(mode="json"))
