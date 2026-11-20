
from pathlib import Path
from typing import Optional

import pytest

_baseurl: Optional[str] = None


@pytest.fixture(scope='session')
def rootdir(request: pytest.FixtureRequest) -> Path:
    return request.config.rootpath


@pytest.fixture(scope='session')
def data(rootdir: Path) -> Path:
    return rootdir.joinpath('data')


@pytest.fixture()
def host(request: pytest.FixtureRequest) -> Optional[str]:
    return _baseurl


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--host", metavar="HOST", default="http://localhost:4000")


def pytest_configure(config: pytest.Config) -> None:
    global _baseurl
    _baseurl = config.getoption('host')
