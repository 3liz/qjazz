"""Client tests for qjazz-map/qjazz-rpc services

These tests require running servers started from
the `qjazz-server/tests` configurations:

    make -C qjazz-server/tests run-rpc
    make -C qjazz-server/tests run-map

Run with:

    pytest [--host HOST[:PORT]]
"""

import pytest

server_host = "localhost:4000"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--host",
        metavar="HOST[:PORT]",
        default=server_host,
        help="server host name (and port)",
    )


def pytest_configure(config: pytest.Config) -> None:
    global server_host
    server_host = config.getoption("host")


@pytest.fixture(scope="session")
def host() -> str:
    return server_host


@pytest.fixture(scope="session")
def backend(host: str) -> str:
    """Url of the 'test' backend"""
    return f"http://{host}/test"


@pytest.fixture(scope="session")
def montpellier(backend: str) -> str:
    """Url of the montpellier dataset in the 'test' backend catalog"""
    return f"{backend}/catalog/%2Fmontpellier%2Fmontpellier"
