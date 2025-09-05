import traceback

from pathlib import Path

import pytest

from qjazz_cache.prelude import CacheManager, ProjectsConfig
from qjazz_core import logger, qgis


@pytest.fixture(scope="session")
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)


@pytest.fixture(scope="session")
def data(rootdir: Path) -> Path:
    return rootdir.joinpath("data")


@pytest.fixture(scope="session")
def plugindir(rootdir: Path) -> Path:
    return rootdir.joinpath("plugins")


@pytest.fixture(scope="session")
def config(data):
    """Setup configuration"""
    conf = ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            "/tests": f"{data}/samples/",
            "/france": f"{data}/france_parts/",
            "/montpellier": f"{data}/montpellier/",
            "/database": "postgresql://?service=qjazz",
            "/mydb": "postgresql://user@myddb?dbname=foo&project={path}",
        },
    )
    CacheManager.initialize_handlers(conf)
    return conf


def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        print("Initializing qgis application")
        qgis.init_qgis_application()
        qgis.init_qgis_processing()
        if logger.is_enabled_for(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        pytest.exit("Qgis installation is required", returncode=1)


def pytest_sessionfinish(session, exitstatus):
    try:
        from qjazz_core import qgis

        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()
