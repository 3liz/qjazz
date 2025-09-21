import os
import traceback

from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

from qjazz_core import logger
from qjazz_core.qgis import Server

from qjazz_rpc.config import (
    ProjectsConfig,
    QgisConfig,
    QgisPluginConfig,
)
from qjazz_rpc.tests import Worker
from qjazz_rpc.worker import Feedback

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
def data(request: pytest.FixtureRequest) -> Path:
    return request.config.rootpath.joinpath("data")


@pytest.fixture(scope="session")
def plugins(request: pytest.FixtureRequest) -> Path:
    return request.config.rootpath.joinpath("plugins")


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
async def worker(projects: ProjectsConfig) -> AsyncGenerator[Worker, None]:
    """Setup configuration"""
    logger.setup_log_handler(None)
    worker = Worker(config=QgisConfig(projects=projects))
    await worker.start()
    yield worker
    await worker.terminate()


@pytest.fixture(scope="session")
def feedback() -> Feedback:
    return Feedback()


# Plugins config
@pytest.fixture(scope="session")
def plugins_config(plugins: Path) -> QgisPluginConfig:
    """Setup configuration"""
    return QgisPluginConfig(
        paths=(plugins,),
    )


# Qgis Config
@pytest.fixture(scope="session")
def qgis_config(projects: ProjectsConfig, plugins_config: QgisPluginConfig) -> QgisConfig:
    return QgisConfig(
        projects=projects,
        plugins=plugins_config,
        use_default_server_handler=False,
    )

# Qgis server
@pytest.fixture(scope="package")
def qgis_server(qgis_config: QgisConfig, feedback: Feedback) -> Generator[Server, None, None]:
    """Return server"""
    from qjazz_core.qgis import PluginType, QgisPluginService

    from qjazz_cache.prelude import CacheManager
    from qjazz_rpc.worker import setup_server

    server = setup_server(qgis_config)

    cm = CacheManager(qgis_config.projects, server.inner)
    cm.register_as_service()

    server_iface = server.inner.serverInterface()

    plugin_s = QgisPluginService(qgis_config.plugins)
    plugin_s.load_plugins(PluginType.SERVER, server_iface)
    plugin_s.register_as_service()

    yield  server

    # Require to prevent crash when releasing server in tests
    # Related to QgsProject::setInstance(NULL) in binding code
    # Neet do investigate what's going on in QGIS
    cm.clear()
