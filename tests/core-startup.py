#
# Startup scripts for tests with ipython
#

from qjazz_contrib.core.qgis import (
    init_qgis_application,
    init_qgis_server,
    show_qgis_settings,
    show_all_versions,
)

from qjazz_contrib.core import logger

logger.setup_log_handler(log_level=logger.LogLevel.TRACE)

from qgis.core import (
    Qgis,
    QgsProject,
    QgsCoordinateReferenceSystem,
)

from qgis.server import (
    QgsServerProjectUtils,
)
