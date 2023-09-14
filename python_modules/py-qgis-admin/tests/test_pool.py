# flake8: noqa
import pytest  # noqa
import asyncio  # noqa

from py_qgis_admin.pool import (  # noqa
    PoolClient,
)

from py_qgis_admin.resolver import (  # noqa
    Resolver,
    DNSResolverConfig,
    DNSResolver,
    SocketResolverConfig,
    ResolverConfig,
)


pytest_plugins = ('pytest_asyncio',)


async def test_resolver_config():
    config = ResolverConfig(
        pools=[
            DNSResolverConfig(
                type="dns",
                host="localhost",
                port=23456,
            ),
            DNSResolverConfig(
                type="dns",
                host="localhost",
                port=23456,
                ipv6=True,
            ),
            SocketResolverConfig(
                type="socket",
                path="/tmp/my.sock",
            ),
        ],
    )

    resolvers = list(config.get_resolvers())
    assert len(resolvers) == 3
    assert resolvers[0].name == "dns:localhost"
    assert resolvers[1].name == "dns:localhost"
    assert resolvers[2].name == "unix:/tmp/my.sock"

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
    
    await pool.update_servers()
    assert len(pool._servers) == 1

    # Clear cache
    await pool.clear_cache()
    # Get cache content
    content =  await pool.cache_content()
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
    rv = await pool.synchronize_caches()
    assert len(rv) == 1
    uri, items = tuple(rv.items())[0]
    assert items[0]['uri'] == uri
    assert items[0]['status'] == 'UNCHANGED'
    assert items[0]['serverAddress'] == '127.0.0.1:23456'



