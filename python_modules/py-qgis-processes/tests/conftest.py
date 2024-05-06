import traceback

from pathlib import Path

import pytest  # noqa

from py_qgis_cache import ProjectsConfig
from py_qgis_contrib.core import qgis
from py_qgis_processes.processing.config import ProcessingConfig


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


def pytest_sessionfinish(session, exitstatus):
    try:
        from py_qgis_contrib.core import qgis
        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()


@pytest.fixture(scope='session')
def cache_config(data: Path) -> ProjectsConfig:
    """ Setup cache configuration
    """
    return ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            '/tests': f'{data}/samples/',
            '/france': f'{data}/france_parts/',
            '/montpellier': f'{data}/montpellier/',
            '/database': 'postgresql://?service=py-qgis',
        },
    )


@pytest.fixture(scope='session')
def processing_config(rootdir: Path, cache_config: ProjectsConfig) -> ProcessingConfig:
    from py_qgis_processes.processing.config import QgisPluginConfig
    return ProcessingConfig(
        projects=cache_config,
        plugins=QgisPluginConfig(
            paths=[rootdir.joinpath('plugins')],
        ),
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
