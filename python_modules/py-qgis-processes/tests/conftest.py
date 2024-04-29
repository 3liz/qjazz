from pathlib import Path

import pytest  # noqa

from py_qgis_contrib.core import logger, qgis


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


def pytest_collection_modifyitems(config, items):
    if not qgis.qgis_initialized():
        skip_qgis = pytest.mark.skip(reason="No qgis environment")
        for item in items:
            if "qgis" in item.keywords:
                item.add_marker(skip_qgis)


@pytest.fixture(scope='session')
def qgis_session(request: pytest.FixtureRequest) -> bool:
    try:
        print("Initialising qgis application")
        qgis.init_qgis_application()
        qgis.init_qgis_processing()
        if logger.isEnabledFor(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        print("No qgis environment found")

    return qgis.qgis_initialized()
