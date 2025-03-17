#
# Copyright 2020 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from .config import HandlerConfig, register_protocol_handler  # noqa F401


def register_default_handlers():
    from .file import FileProtocolHandler  # noqa F401
    from .postgresql import PostgresHandler  # noqa F401
    from .geopackage import GeoPackageHandler  # noqa F401

    pass
