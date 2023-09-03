import pytest

from pathlib import Path
from py_qgis_contrib.core import qgis, logger


@pytest.fixture(scope='session')
def plugindir(request):
    return Path(request.config.rootdir.strpath)/'plugins'


def pytest_collection_modifyitems(config, items):
    if not qgis.qgis_initialized():
        skip_qgis = pytest.mark.skip(reason="No qgis environment")
        for item in items:
            if "qgis" in item.keywords:
                item.add_marker(skip_qgis)


def pytest_sessionstart(session):
    try:
        print("Initialising qgis application")
        qgis.init_qgis_application()
        qgis.init_qgis_processing()
        if logger.isEnabledFor(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        print("No qgis environment found")
