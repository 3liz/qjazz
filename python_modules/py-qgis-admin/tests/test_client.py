import pytest
import asyncio  # noqa

from py_qgis_admin.client import (
    ClientConfig,
    PoolItemClient,
)

pytest_plugins = ('pytest_asyncio',)


def test_clientconfig():

    config = ClientConfig(server_address=('127.0.0.1',  23456))
    assert config.address_to_string() == '127.0.0.1:23456'

    config = ClientConfig(server_address='unix:/tmp/qgis/server.sock')
    assert config.address_to_string() == 'unix:/tmp/qgis/server.sock'


@pytest.mark.server
async def test_client():

    config = ClientConfig(server_address=("::", 23456))
    client = PoolItemClient(config)

    async for resp in client.ping("hello", timeout=2):
        assert resp == "hello"

    stats = await client.stats()

    await client.clear_cache()

    count = 0
    async for item in client.catalog():
        print("* Catalog:", item.uri)
        count += 1

    print("\nCatalog items:", count)
    assert count > 0

    count = 0
    async for item in client.pull_projects("/france/france_parts.qgs"):
        print("* Pulled:", item.uri)
        count += 1

    assert count == stats.num_workers
