import pytest

from py_qgis_contrib.core import qgis


def pytest_collection_modifyitems(config, items):
    if not qgis.qgis_application:
        skip_qgis = pytest.mark.skip(reason="No qgis environment")
        for item in items:
            if "qgis" in item.keywords:
                item.add_marker(skip_qgis)


def pytest_sessionstart(session):
    try:
        print("Initialising qgis application")
        qgis.init_qgis_application()
    except ModuleNotFoundError:
        print("No qgis environment found")
