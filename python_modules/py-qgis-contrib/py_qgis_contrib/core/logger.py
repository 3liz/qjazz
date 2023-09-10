#
# Copyright 2018-2023 3liz
# Author: David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
""" Logger
"""
import os
import sys
import logging
from contextlib import contextmanager
from enum import Enum

from typing_extensions import (
    Optional,
    Annotated,
)

from pydantic import (
    Field,
    PlainValidator,
    PlainSerializer,
    WithJsonSchema,
)


from . import config

LOGGER = logging.getLogger('py-qgis-logger')

REQ_LOG_TEMPLATE = "{ip}\t{code}\t{method}\t{url}\t{time}\t{length}\t"
REQ_FORMAT = REQ_LOG_TEMPLATE + '{agent}\t{referer}'
RREQ_FORMAT = REQ_LOG_TEMPLATE


class LogLevel(Enum):
    NOTSET = logging.NOTSET
    TRACE = logging.DEBUG-1
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    REQ = logging.INFO+1
    RREQ = logging.INFO+2
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


FORMATSTR = '%(asctime)s\t[%(process)d]\t%(levelname)s\t%(message)s'


@config.section('logging')
class LoggingConfig(config.Config):
    level: Annotated[
        LogLevel,
        PlainValidator(lambda v: LogLevel[v]),
        PlainSerializer(lambda x: x.name, return_type=str),
        WithJsonSchema({
            'enum': [m for m in LogLevel.__members__],
            'type': 'str'
        }),
        Field(default="INFO", validate_default=True)
    ]


def set_log_level(log_level: Optional[LogLevel] = None):
    """ Set the log level
    """
    log_level = log_level or config.confservice.conf.logging.level
    LOGGER.setLevel(log_level.value)


def setup_log_handler(
    log_level: Optional[LogLevel] = None,
    channel: Optional[logging.Handler] = None,
):
    """ Initialize log handler with the given log level
    """
    logging.addLevelName(LogLevel.REQ.value, LogLevel.REQ.name)
    logging.addLevelName(LogLevel.RREQ.value, LogLevel.RREQ.name)

    set_log_level(log_level)

    formatter = logging.Formatter(FORMATSTR)
    channel = channel or logging.StreamHandler(sys.stderr)
    channel.setFormatter(formatter)

    LOGGER.addHandler(channel)


@contextmanager
def logfile_context(workdir: str, basename: str):
    """ Add a temporary file handler
    """
    logfile = os.path.join(workdir, "%s.log" % basename)
    channel = logging.FileHandler(logfile)
    formatter = logging.Formatter(FORMATSTR)
    channel.setFormatter(formatter)
    LOGGER.addHandler(channel)
    try:
        yield
    finally:
        LOGGER.removeHandler(channel)
        channel.close()


def format_log_request(handler):
    """ Format current request from the given tornado request handler

        :return a tuple (fmt,code,reqtime,length) where:
            fmt: the log string
            code: the http return code
            reqtime: the request time
            length: the size of the payload
    """
    request = handler.request
    code = handler.get_status()
    reqtime = request.request_time()

    length = handler._headers.get('Content-Length') or -1
    agent = request.headers.get('User-Agent') or ""
    referer = request.headers.get('Referer') or ""

    fmt = REQ_FORMAT.format(
        ip=request.remote_ip,
        method=request.method,
        url=request.uri,
        code=code,
        time=int(1000.0 * reqtime),
        length=length,
        referer=referer,
        agent=agent)

    return fmt, code, reqtime, length


def log_request(handler):
    """ Log the current request

        :param code: The http return code
        :param reqtiem: The request time

        :return A tuple (code,reqtime,length) where:
            code: the http retudn code
            reqtime: the request time
            length: the size of the payload
    """
    fmt, code, reqtime, length = format_log_request(handler)
    LOGGER.log(LogLevel.REQ.value, fmt)
    return code, reqtime, length


def format_log_rrequest(response):
    """ Format current r-request from the given response

        :param response: The response returned from the request
        :return A tuple (fmt,code,reqtime,length) where:
            fmt: the log string
            code: the http retudn code
            reqtime: the request time
            length: the size of the payload
    """
    request = response.request
    code = response.code
    reqtime = response.request_time

    length = -1
    try:
        length = response.headers['Content-Length']
    except KeyError:
        pass

    fmt = RREQ_FORMAT.format(
        ip='',
        method=request.method,
        url=request.url,
        code=code,
        time=int(1000.0 * reqtime),
        length=length)

    return fmt, code, reqtime, length


def log_rrequest(response):
    """ Log the current response request from the given response

        :param response: The response returned from the request
        :return A tuple (code,reqtime,length) where:
            code: the http retudn code
            reqtime: the request time
            length: the size of the payload
    """
    fmt, code, reqtime, length = format_log_rrequest(response)
    LOGGER.log(LogLevel.RREQ.value, fmt)
    return code, reqtime, length


#
# Shortcuts
#

warning = LOGGER.warning
info = LOGGER.info
error = LOGGER.error
critical = LOGGER.critical
debug = LOGGER.debug


def trace(msg, *args, **kwargs):
    LOGGER.log(LogLevel.TRACE.value, msg, *args, **kwargs)


def isEnabledFor(level: LogLevel):
    return LOGGER.isEnabledFor(level.value)
