#
# Startup scripts for tests with ipython
#

from qjazz_contrib.core.qgis import (
    init_qgis_application,
    init_qgis_server,
)

from qjazz_contrib.core import logger

logger.setup_log_handler(log_level=logger.LogLevel.TRACE)

