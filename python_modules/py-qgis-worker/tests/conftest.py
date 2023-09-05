import pytest  # noqa

from pathlib import Path


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')
