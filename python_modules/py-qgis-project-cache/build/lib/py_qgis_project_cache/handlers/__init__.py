#
# Copyright 2020 3liz
# Author David Marteau
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from .file import *  # noqa: F403,F401
from .storage import init_storage_handlers  # noqa: F403,F401

__all__ = ['init_storage_handlers']
