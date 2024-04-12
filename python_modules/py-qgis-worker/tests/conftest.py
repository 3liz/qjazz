from pathlib import Path

import pytest

from py_qgis_worker.config import ProjectsConfig


@pytest.fixture(scope='session')
def data(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath, 'data')


@pytest.fixture(scope='session')
def projects(data: Path) -> ProjectsConfig:
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
        },
    )
