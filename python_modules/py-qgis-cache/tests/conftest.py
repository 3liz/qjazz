import pytest  # noqa
import traceback

from pathlib import Path
from py_qgis_cache import ProjectsConfig


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


@pytest.fixture(scope='session')
def config(data):
    """ Setup configuration
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
        }
    )


def pytest_sessionstart(session):
    try:
        from py_qgis_contrib.core import qgis
        qgis.init_qgis_application()
        from py_qgis_cache import CacheManager
        CacheManager.initialize_handlers()
    except ModuleNotFoundError:
        pytest.exit("Qgis installation is required", returncode=1)


def pytest_sessionfinish(session, exitstatus):
    try:
        from py_qgis_contrib.core import qgis
        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()
