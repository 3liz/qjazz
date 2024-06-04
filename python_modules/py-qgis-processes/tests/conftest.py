import sys

from pathlib import Path

import pytest

from py_qgis_cache import ProjectsConfig
from py_qgis_contrib.core import qgis
from py_qgis_processes.processing.config import ProcessingConfig


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
            '/database': 'postgresql://?service=py-qgis',
        },
    )


@pytest.fixture(scope='session')
def processing_config(rootdir: Path, workdir: Path, cache_config: ProjectsConfig) -> ProcessingConfig:
    from py_qgis_processes.processing.config import QgisPluginConfig
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
    from py_qgis_processes.processing.config import QgisPluginConfig
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


@pytest.fixture(scope='session')
def cache_manager(cache_config, qgis_session):
    from py_qgis_cache import CacheManager

    CacheManager.initialize_handlers()
    return CacheManager(cache_config)


@pytest.fixture(scope='session')
def projects(cache_manager):
    """ Return wrapper around cache manager
    """
    from qgis.core import QgsProject

    from py_qgis_cache import CheckoutStatus as Co

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
