from pathlib import Path

import pytest  # noqa


@pytest.fixture(scope='session')
def data(request):
    return Path(request.config.rootdir.strpath, 'data')


