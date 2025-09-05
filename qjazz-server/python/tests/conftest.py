import os
import traceback

from pathlib import Path

import pytest

from qjazz_core import logger

from qjazz_rpc.config import ProjectsConfig, QgisConfig
from qjazz_rpc.tests import Worker

# Disable loglevel setting notice
os.environ["QJAZZ_LOGLEVEL_NOTICE"] = "no"


def pytest_collection_modifyitems(config, items):
    keywordexpr = config.option.keyword
    markexpr = config.option.markexpr
    if keywordexpr or markexpr:
        return  # let pytest handle this

    skip_server = pytest.mark.skip(reason="server tests not enabled")
    for item in items:
        if "server" in item.keywords:
            item.add_marker(skip_server)


def pytest_sessionfinish(session, exitstatus):
    try:
        from qjazz_core import qgis

        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()


@pytest.fixture(scope="session")
def qgis_session(request: pytest.FixtureRequest) -> None:
    from qjazz_core import logger, qgis

    try:
        print("Initializing qgis application")
        qgis.init_qgis_application()
        if logger.is_enabled_for(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        pytest.exit("Qgis installation is required", returncode=1)

    return None


@pytest.fixture(scope="session")
def data(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath, "data")


@pytest.fixture(scope="session")
def projects(data: Path) -> ProjectsConfig:
    """Setup configuration"""
    return ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            "/tests": f"{data}/samples/",
            "/france": f"{data}/france_parts/",
            "/montpellier": f"{data}/montpellier/",
        },
    )


@pytest.fixture(scope="function")
async def worker(projects: ProjectsConfig) -> Worker:
    """Setup configuration"""
    logger.setup_log_handler(None)
    worker = Worker(config=QgisConfig(projects=projects))
    await worker.start()
    yield worker
    await worker.terminate()
