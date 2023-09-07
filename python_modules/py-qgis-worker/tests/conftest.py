import pytest  # noqa

from pathlib import Path


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


@pytest.fixture(scope='session')
def config(data):
    """ Setup configuration
    """
    from py_qgis_worker.config import (
        WorkerConfig,
        ProjectsConfig,
    )
    return WorkerConfig(
        name="Test",
        projects=ProjectsConfig(
            trust_layer_metadata=True,
            disable_getprint=True,
            force_readonly_layers=True,
            search_paths={
                '/tests': f'{data}/samples/',
                '/france': f'{data}/france_parts/',
                '/montpellier': f'{data}/montpellier/',
            },
        ),
    )
