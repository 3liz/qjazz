from ipaddress import IPv4Address, IPv6Address

import pytest

from qjazz_admin.pool import PoolClient
from qjazz_admin.resolvers import (
    Resolver,
    ResolverConfig,
)

pytest_plugins = ("pytest_asyncio",)


async def test_resolver_config():
    config = ResolverConfig(
        resolvers=[
            Resolver(
                label="resolver_1",
                address=("localhost", 23456),
            ),
            Resolver(
                label="resolver_2",
                address=("localhost", 23456),
                ipv6=True,
            ),
        ],
    )

    resolvers = config.resolvers
    assert len(resolvers) == 2
    assert resolvers[0].resolver_address() == "localhost:23456"
    assert resolvers[1].resolver_address() == "localhost:23456"

    configs = list(await resolvers[0].backends)
    assert len(configs) == 1
    assert configs[0].server_address == (IPv4Address("127.0.0.1"), 23456)

    configs = list(await resolvers[1].backends)
    assert len(configs) == 1
    assert configs[0].server_address == (IPv6Address("::1"), 23456)


@pytest.mark.server
async def test_pool():
    resolver = Resolver(
        address=("localhost", 23456),
    )

    pool = PoolClient(resolver)
    assert len(pool._servers) == 0

    await pool.update_backends()
    assert len(pool._bakcends) == 1

    # Clear cache
    await pool.clear_cache()
    # Get cache content
    content = await pool.cache_content()
    assert len(content) == 0

    # Pull project
    rv = await pool.pull_projects("/france/france_parts.qgs")
    assert len(rv) == 1
    uri, items = next(iter(rv.items()))
    assert items[0]["uri"] == uri
    assert items[0]["status"] == "NEW"
    assert items[0]["serverAddress"] == "127.0.0.1:23456"

    # Synchronize
    # If there is only one server in the pool
    # there is not much to synchronize
    rv = await pool.synchronize_cache()
    assert len(rv) == 1
    uri, items = next(iter(rv.items()))
    assert items[0]["uri"] == uri
    assert items[0]["status"] == "UNCHANGED"
    assert items[0]["serverAddress"] == "127.0.0.1:23456"
