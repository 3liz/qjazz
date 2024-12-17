import traceback

from pathlib import Path

import pytest

from qjazz_cache.prelude import CacheManager, ProjectsConfig


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


@pytest.fixture(scope='session')
def config(data):
    """ Setup configuration
    """
    conf = ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            '/tests': f'{data}/samples/',
            '/france': f'{data}/france_parts/',
            '/montpellier': f'{data}/montpellier/',
            '/database': 'postgresql://?service=qjazz',
            '/mydb': 'postgresql://user@myddb?dbname=foo&project={path}',
        },
    )
    CacheManager.initialize_handlers(conf)
    return conf


def pytest_sessionstart(session):
    try:
        from qjazz_contrib.core import qgis
        qgis.init_qgis_application()
    except ModuleNotFoundError:
        pytest.exit("Qgis installation is required", returncode=1)


def pytest_sessionfinish(session, exitstatus):
    try:
        from qjazz_contrib.core import qgis
        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()
