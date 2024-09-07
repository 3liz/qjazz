from pathlib import Path

import pytest

from py_qgis_rpc.config import ProjectsConfig


def pytest_collection_modifyitems(config, items):
    keywordexpr = config.option.keyword
    markexpr = config.option.markexpr
    if keywordexpr or markexpr:
        return  # let pytest handle this

    skip_server = pytest.mark.skip(reason='server tests not enabled')
    for item in items:
        if 'server' in item.keywords:
            item.add_marker(skip_server)


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
