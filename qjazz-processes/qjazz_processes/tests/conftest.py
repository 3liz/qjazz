import os
import sys
import traceback

from pathlib import Path
from typing import Callable, Generator, Protocol, cast

import pytest

from aiohttp import web
from aiohttp.test_utils import TestClient

from qgis.core import (
    Qgis,
    QgsProcessingFeedback,
    QgsProject,
)
from qgis.server import QgsServer

from qjazz_cache.prelude import CacheManager, ProjectsConfig
from qjazz_contrib.core import qgis
from qjazz_processes.processing.prelude import (
    ProcessingConfig,
    ProcessingContext,
)

from .utils import Feedback, Projects


def pytest_report_header(config):
    from osgeo import gdal

    from qgis.core import Qgis
    from qgis.PyQt import Qt

    gdal_version = gdal.VersionInfo("VERSION_NUM")
    return (
        f"QGIS : {Qgis.QGIS_VERSION_INT}\n"
        f"Python GDAL : {gdal_version}\n"
        f"Python : {sys.version}\n"
        f"QT : {Qt.QT_VERSION_STR}"
    )


@pytest.fixture(scope="session")
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)  # type: ignore [attr-defined]


@pytest.fixture(scope="session")
def data(rootdir: Path) -> Path:
    return rootdir.joinpath("data")


@pytest.fixture(scope="session")
def workdir(rootdir: Path) -> Path:
    path = rootdir.joinpath("__workdir__")
    path.mkdir(exist_ok=True)
    return path


def pytest_sessionstart(session: pytest.Session):
    workdir = Path(session.startdir).joinpath("__workdir__")  # type: ignore [attr-defined]
    if workdir.exists():
        import shutil

        shutil.rmtree(workdir)


@pytest.fixture(scope="session")
def processing_config(rootdir: Path, workdir: Path, cache_config: ProjectsConfig) -> ProcessingConfig:
    from qjazz_processes.processing.config import QgisPluginConfig

    return ProcessingConfig(
        workdir=workdir,
        projects=cache_config,
        plugins=QgisPluginConfig(
            paths=[rootdir.joinpath("plugins")],
        ),
    )


@pytest.fixture(scope="session")
def processing_raw_config(
    rootdir: Path,
    workdir: Path,
    cache_config: ProjectsConfig,
) -> ProcessingConfig:
    from qjazz_processes.processing.config import QgisPluginConfig

    return ProcessingConfig(
        workdir=workdir,
        projects=cache_config,
        plugins=QgisPluginConfig(
            paths=[rootdir.joinpath("plugins")],
        ),
        raw_destination_input_sink=True,
        raw_destination_root_path=workdir,
    )


@pytest.fixture(scope="session")
def qgis_session(processing_config: ProcessingConfig) -> ProcessingConfig:
    try:
        print("Initialising qgis application")
        qgis.init_qgis_application(settings=processing_config.settings())
        qgis.init_qgis_processing()
        # print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        print("No qgis environment found")

    assert qgis.qgis_initialized()
    return processing_config


@pytest.fixture(scope="function")
def feedback() -> QgsProcessingFeedback:
    return Feedback()


@pytest.fixture(scope="function")
def context(qgis_session: ProcessingConfig, feedback: QgsProcessingFeedback) -> ProcessingContext:
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    # Create the default workdir
    context.workdir.mkdir(exist_ok=True)

    return context


@pytest.fixture(scope="function")
def server(qgis_session: ProcessingConfig) -> QgsServer:
    os.environ["QGIS_SERVER_PROJECT_CACHE_STRATEGY"] = "off"
    return QgsServer()


@pytest.fixture(scope="session")
def cache_manager(cache_config: ProjectsConfig, qgis_session: ProcessingConfig) -> CacheManager:
    CacheManager.initialize_handlers(cache_config)
    return CacheManager(cache_config)


class ProjectsProto(Protocol):
    def get(self, name: str) -> QgsProject: ...


@pytest.fixture(scope="session")
def projects(cache_manager: CacheManager) -> Generator[ProjectsProto, None, None]:
    """Return wrapper around cache manager"""
    from qjazz_cache.prelude import CheckoutStatus as Co
    from qjazz_cache.prelude import ProjectMetadata

    cm = cache_manager

    class ProjectsImpl(Projects):
        def get(self, name: str) -> QgsProject:
            # Resolve location
            url = cm.resolve_path(name)
            # Check status
            md, status = cm.checkout(url)
            match status:
                case Co.REMOVED | Co.NOTFOUND:
                    raise FileNotFoundError(f"Project {url} not found")
                case _:
                    entry, _ = cm.update(cast(ProjectMetadata, md), status)
                    project = entry.project
            return project

    yield ProjectsImpl()

    print("Deleting projects cache")
    cm.clear()


@pytest.fixture(scope="session")
def plugins(qgis_session: ProcessingConfig) -> qgis.QgisPluginService:
    """ """
    plugin_service = qgis.QgisPluginService(qgis_session.plugins)
    plugin_service.load_plugins(qgis.PluginType.PROCESSING, None)
    plugin_service.register_as_service()
    return plugin_service


@pytest.fixture(scope="function")
def server_app(rootdir: Path) -> web.Application:
    from qjazz_processes.server import cli, server

    return server.create_app(
        cli.load_configuration(rootdir.joinpath("server-config.toml")),
    )


@pytest.fixture(scope="function")
async def http_client(server_app: web.Application, aiohttp_client: Callable) -> TestClient:
    return await aiohttp_client(server_app)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        from qjazz_contrib.core import qgis
        # On QGIS <= 3.34, explicite call to exit() is required
        # in order to prevent a segmentation fault.
        if Qgis.QGIS_VERSION_INT <= 34000:
            qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()
