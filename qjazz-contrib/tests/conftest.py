import traceback

from pathlib import Path

import pytest

from qjazz_cache.prelude import CacheManager, ProjectsConfig
from qjazz_core import logger, qgis
from qjazz_store import store


@pytest.fixture(scope="session")
def rootdir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootdir.strpath)


@pytest.fixture(scope="session")
def data(rootdir: Path) -> Path:
    return rootdir.joinpath("data")


@pytest.fixture(scope="session")
def plugindir(rootdir: Path) -> Path:
    return rootdir.joinpath("plugins")


@pytest.fixture(scope="session")
def config(data):
    """Setup configuration"""
    conf = ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            "/tests": f"{data}/samples/",
            "/france": f"{data}/france_parts/",
            "/montpellier": f"{data}/montpellier/",
            "/database": "postgresql://?service=qjazz",
            "/mydb": "postgresql://user@myddb?dbname=foo&project={path}",
        },
    )
    CacheManager.initialize_handlers(conf)
    return conf


def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        print("Initializing qgis application")
        qgis.init_qgis_application()
        qgis.init_qgis_processing()
        if logger.is_enabled_for(logger.LogLevel.DEBUG):
            print(qgis.show_qgis_settings())
    except ModuleNotFoundError:
        pytest.exit("Qgis installation is required", returncode=1)


def pytest_sessionfinish(session, exitstatus):
    try:
        from qjazz_core import qgis

        qgis.exit_qgis_application()
    except Exception:
        traceback.print_exc()


@pytest.fixture(scope="session")
def store_endpoint() -> str:
    return "localhost:9000"


@pytest.fixture(scope="session")
def store_creds(store_endpoint: str) -> store.StoreCreds:
    return store.StoreCreds(
        endpoint=store_endpoint,
        access_key="qjazzadmin",
        secret_key="qjazzadmin",
        secure=False,
    )


@pytest.fixture(scope="session")
def store_client(store_creds: store.StoreCreds) -> store.StoreClient:
    m = store.store_client(store_creds)
    if not m.bucket_exists("dev"):
        m.make_bucket("dev")
    return m
