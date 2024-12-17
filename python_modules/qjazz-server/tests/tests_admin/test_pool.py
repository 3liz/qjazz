# flake8: noqa
import asyncio  # noqa

import pytest  # noqa

from qjazz_admin.pool import PoolClient  # noqa
from qjazz_admin.resolvers import (  # noqa
    DNSResolver,
    DNSResolverConfig,
    Resolver,
    ResolverConfig,
    SocketResolverConfig,
)

pytest_plugins = ('pytest_asyncio',)


async def test_resolver_config():
    config = ResolverConfig(
        pools=[
            DNSResolverConfig(
                label="resolver_1",
                type="dns",
                host="localhost",
                port=23456,
            ),
            DNSResolverConfig(
                label="resolver_2",
                type="dns",
                host="localhost",
                port=23456,
                ipv6=True,
            ),
            SocketResolverConfig(
                label="resolver_3",
                type="socket",
                address="unix:/tmp/my.sock",
            ),
        ],
    )

    resolvers = list(config.get_resolvers())
    assert len(resolvers) == 3
    assert resolvers[0].address == "localhost:23456"
    assert resolvers[1].address == "localhost:23456"
    assert resolvers[2].address == "unix:/tmp/my.sock"

    configs = list(await resolvers[0].configs)
    assert len(configs) == 1
    assert configs[0].server_address == ("127.0.0.1", 23456)

    configs = list(await resolvers[1].configs)
    assert len(configs) == 1
    assert configs[0].server_address == ("[::1]", 23456)

    configs = list(await resolvers[2].configs)
    assert len(configs) == 1
    assert configs[0].server_address == "unix:/tmp/my.sock"


@pytest.mark.server
async def test_pool():
    resolver = DNSResolver(DNSResolverConfig(
        type="dns",
        host="localhost",
        port=23456,
    ))

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
    uri, items = tuple(rv.items())[0]
    assert items[0]['uri'] == uri
    assert items[0]['status'] == 'NEW'
    assert items[0]['serverAddress'] == '127.0.0.1:23456'

    # Synchronize
    # If there is only one server in the pool
    # there is not much to synchronize
    rv = await pool.synchronize_cache()
    assert len(rv) == 1
    uri, items = tuple(rv.items())[0]
    assert items[0]['uri'] == uri
    assert items[0]['status'] == 'UNCHANGED'
    assert items[0]['serverAddress'] == '127.0.0.1:23456'
