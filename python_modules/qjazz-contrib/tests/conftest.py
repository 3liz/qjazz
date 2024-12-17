from pathlib import Path

import pytest

from qjazz_contrib.core import logger, qgis


@pytest.fixture(scope='session')
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)


@pytest.fixture(scope='session')
def plugindir(rootdir: Path) -> Path:
    return rootdir / 'plugins'


def pytest_collection_modifyitems(config, items):
    if not qgis.qgis_initialized():
        skip_qgis = pytest.mark.skip(reason="No qgis environment")
        for item in items:
            if "qgis" in item.keywords:
                item.add_marker(skip_qgis)


def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        print("Initialising qgis application")
        qgis.init_qgis_application()
        qgis.init_qgis_processing()
        if logger.is_enabled_for(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        print("No qgis environment found")
