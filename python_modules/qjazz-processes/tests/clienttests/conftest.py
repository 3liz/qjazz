
from pathlib import Path
from string import Template

import pytest

_baseurl = None


@pytest.fixture(scope='session')
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)


@pytest.fixture(scope='session')
def data(rootdir: Path) -> Path:
    return rootdir.joinpath('data')


@pytest.fixture()
def host(request):
    return _baseurl


def pytest_addoption(parser):
    parser.addoption("--host", metavar="HOST", default="http://localhost:4000")


def pytest_configure(config):
    global _baseurl
    _baseurl = config.getoption('host')
