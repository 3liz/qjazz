from pathlib import Path

import pytest


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
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


@pytest.fixture(scope='session')
def config(data):
    """ Setup configuration
    """
    from py_qgis_admin.config import ServiceConfig
    return ServiceConfig()
