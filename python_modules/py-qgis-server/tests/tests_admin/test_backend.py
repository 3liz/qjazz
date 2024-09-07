import asyncio  # noqa

import pytest

from py_qgis_admin.backend import Backend, BackendConfig

pytest_plugins = ('pytest_asyncio',)


def test_clientconfig():

    config = BackendConfig(server_address=('127.0.0.1', 23456))
    assert config.address_to_string() == '127.0.0.1:23456'

    config = BackendConfig(server_address='unix:/tmp/qgis/server.sock')
    assert config.address_to_string() == 'unix:/tmp/qgis/server.sock'


@pytest.mark.server
async def test_backend():

    config = BackendConfig(server_address=("::", 23456))
    backend = Backend(config)

    async for resp in backend.ping("hello", timeout=2):
        assert resp == "hello"

    stats = await backend.stats()

    await backend.clear_cache()

    count = 0
    async for item in backend.catalog():
        print("* Catalog:", item.uri)
        count += 1

    print("\nCatalog items:", count)
    assert count > 0

    count = 0
    async for item in backend.pull_projects("/france/france_parts.qgs"):
        print("* Pulled:", item.uri)
        count += 1

    assert count == stats.num_workers
