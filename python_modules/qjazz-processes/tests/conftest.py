import sys

from pathlib import Path

import pytest

from aiohttp import web
from aiohttp.test_utils import TestClient
from typing_extensions import Callable

from qgis.core import (
    QgsProcessingFeedback,
)

from qjazz_cache.prelude import ProjectsConfig
from qjazz_contrib.core import qgis
from qjazz_processes.processing.prelude import (
    ProcessingConfig,
    ProcessingContext,
)

from .utils import FeedBack


def pytest_report_header(config):
    from osgeo import gdal

    from qgis.core import Qgis
    from qgis.PyQt import Qt

    gdal_version = gdal.VersionInfo('VERSION_NUM')
    return (
        f"QGIS : {Qgis.QGIS_VERSION_INT}\n"
        f"Python GDAL : {gdal_version}\n"
        f"Python : {sys.version}\n"
        f"QT : {Qt.QT_VERSION_STR}"
    )


@pytest.fixture(scope='session')
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)


@pytest.fixture(scope='session')
def data(rootdir: Path) -> Path:
    return rootdir.joinpath('data')


@pytest.fixture(scope='session')
def workdir(rootdir: Path) -> Path:
    path = rootdir.joinpath('__workdir__')
    path.mkdir(exist_ok=True)
    return path


def pytest_collection_modifyitems(config, items):
    if not qgis.qgis_initialized():
        skip_qgis = pytest.mark.skip(reason="No qgis environment")
        for item in items:
            if "qgis" in item.keywords:
                item.add_marker(skip_qgis)


def pytest_sessionstart(session: pytest.Session):
    workdir = Path(session.startdir).joinpath('__workdir__')
    if workdir.exists():
        import shutil
        shutil.rmtree(workdir)


@pytest.fixture(scope='session')
def cache_config(data: Path) -> ProjectsConfig:
    """ Setup cache configuration
    """
    return ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            '/samples': f'{data}/samples/',
            '/france': f'{data}/france_parts/',
            '/montpellier': f'{data}/montpellier/',
            '/database': 'postgresql://?service=qjazz',
        },
    )


@pytest.fixture(scope='session')
def processing_config(rootdir: Path, workdir: Path, cache_config: ProjectsConfig) -> ProcessingConfig:
    from qjazz_processes.processing.config import QgisPluginConfig
    return ProcessingConfig(
        workdir=workdir,
        projects=cache_config,
        plugins=QgisPluginConfig(
            paths=[rootdir.joinpath('plugins')],
        ),
    )


@pytest.fixture(scope='session')
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
            paths=[rootdir.joinpath('plugins')],
        ),
        raw_destination_input_sink=True,
        raw_destination_root_path=workdir,
    )


@pytest.fixture(scope='session')
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
    return FeedBack()


@pytest.fixture(scope="function")
def context(qgis_session: ProcessingConfig, feedback: QgsProcessingFeedback) -> ProcessingContext:
    context = ProcessingContext(qgis_session)
    context.setFeedback(feedback)

    # Create the default workdir
    context.workdir.mkdir(exist_ok=True)

    return context


@pytest.fixture(scope='session')
def cache_manager(cache_config, qgis_session):
    from qjazz_cache.prelude import CacheManager

    CacheManager.initialize_handlers(cache_config)
    return CacheManager(cache_config)


@pytest.fixture(scope='session')
def projects(cache_manager):
    """ Return wrapper around cache manager
    """
    from qgis.core import QgsProject

    from qjazz_cache.prelude import CheckoutStatus as Co

    cm = cache_manager

    class Project:
        def get(self, name: str) -> QgsProject:
            # Resolve location
            url = cm.resolve_path(name)
            # Check status
            md, status = cm.checkout(url)
            match status:
                case Co.REMOVED | Co.NOTFOUND:
                    raise FileNotFoundError(f"Project {url} not found")
                case _:
                    entry, _ = cm.update(md, status)
                    project = entry.project
            return project

    yield Project()

    print("Deleting projects cache")
    cm.clear()


@pytest.fixture(scope='session')
def plugins(qgis_session: ProcessingConfig) -> qgis.QgisPluginService:
    """
    """
    plugin_service = qgis.QgisPluginService(qgis_session.plugins)
    plugin_service.load_plugins(qgis.PluginType.PROCESSING, None)
    plugin_service.register_as_service()
    return plugin_service


@pytest.fixture(scope='function')
def server_app(rootdir: Path) -> web.Application:
    from qjazz_processes.server import cli, server

    return server.create_app(
        cli.load_configuration(rootdir.joinpath('server-config.toml')),
    )


@pytest.fixture(scope='function')
async def http_client(server_app: web.Application, aiohttp_client: Callable) -> TestClient:
    return await aiohttp_client(server_app)
