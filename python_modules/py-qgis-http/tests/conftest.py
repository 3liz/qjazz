from pathlib import Path

import pytest  # noqa


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
def config(request):
    """ Setup configuration
    """
    from py_qgis_http.config import (
        add_configuration_sections,
        load_configuration,
    )

    add_configuration_sections()
    configpath = Path(request.config.rootdir.strpath, "config.toml")
    return load_configuration(configpath)
