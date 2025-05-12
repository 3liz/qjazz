#
# Copyright 2018-2023 3liz
# Author: David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Logger"""

import logging
import os
import sys

from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

from pydantic import Field, PlainSerializer, PlainValidator, WithJsonSchema

from . import config

LOGGER = logging.getLogger("qjazz")


class LogLevel(Enum):
    NOTSET = logging.NOTSET
    TRACE = logging.DEBUG - 1
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    REQ = logging.INFO + 1
    RREQ = logging.INFO + 2
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    NOTICE = logging.CRITICAL + 1


FORMATSTR = "%(asctime)s.%(msecs)03dZ\t[%(process)d]\t%(levelname)s\t%(message)s"


def _validate_log_level(v: str | LogLevel) -> LogLevel:
    try:
        return LogLevel[v.upper()] if isinstance(v, str) else v
    except KeyError:
        raise ValueError(f"Invalid log level value '{v}'")


@config.section("logging")
class LoggingConfig(config.ConfigBase):
    level: Annotated[
        LogLevel,
        PlainValidator(_validate_log_level),
        PlainSerializer(lambda x: x.name, return_type=str),
        WithJsonSchema(
            {
                "enum": [m for m in LogLevel.__members__],
                "type": "str",
            }
        ),
        Field(default="INFO", validate_default=True),
    ]


def set_log_level(log_level: LogLevel) -> LogLevel:
    """Set the log level"""
    LOGGER.setLevel(log_level.value)
    if os.getenv("QJAZZ_LOGLEVEL_NOTICE") != "no":
        LOGGER.log(LogLevel.NOTICE.value, "Log level set to %s", log_level.name)
    return log_level


def setup_log_handler(
    log_level: Optional[LogLevel] = LogLevel.INFO,
    channel: Optional[logging.Handler] = None,
) -> LogLevel:
    """Initialize log handler with the given log level

    If log_level is None, use the default logging level.
    """

    logging.addLevelName(LogLevel.TRACE.value, LogLevel.TRACE.name)
    logging.addLevelName(LogLevel.REQ.value, LogLevel.REQ.name)
    logging.addLevelName(LogLevel.RREQ.value, LogLevel.RREQ.name)
    logging.addLevelName(LogLevel.NOTICE.value, LogLevel.NOTICE.name)

    log_level = set_log_level(log_level or LogLevel(logging.getLogger().level))

    formatter = logging.Formatter(FORMATSTR, datefmt="%Y-%m-%dT%H:%M:%S")
    channel = channel or logging.StreamHandler(sys.stderr)
    channel.setFormatter(formatter)

    LOGGER.addHandler(channel)
    return log_level


@contextmanager
def logfile(workdir: Path, basename: str):
    """Temporary logging to file"""
    logfile = workdir.joinpath(f"{basename}.log")
    channel = logging.FileHandler(logfile)
    formatter = logging.Formatter(FORMATSTR)
    channel.setFormatter(formatter)
    LOGGER.addHandler(channel)
    try:
        yield
    except Exception as err:
        LOGGER.error("Unhandled exception: %s", err)
        raise
    finally:
        LOGGER.removeHandler(channel)
        channel.close()


#
# Shortcuts
#
warning = LOGGER.warning
info = LOGGER.info
error = LOGGER.error
critical = LOGGER.critical
debug = LOGGER.debug


def notice(msg, *args, **kwargs):
    LOGGER.log(LogLevel.NOTICE.value, msg, *args, **kwargs)


def logger():
    return LOGGER


def trace(msg, *args, **kwargs):
    LOGGER.log(LogLevel.TRACE.value, msg, *args, **kwargs)


def log_req(msg, *args, **kwargs):
    LOGGER.log(LogLevel.REQ.value, msg, *args, **kwargs)


def log_rreq(msg, *args, **kwargs):
    LOGGER.log(LogLevel.RREQ.value, msg, *args, **kwargs)


def is_enabled_for(level: LogLevel) -> bool:
    return LOGGER.isEnabledFor(level.value)


def log_level() -> LogLevel:
    return LogLevel(LOGGER.level)
