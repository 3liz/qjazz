
from urllib.parse import parse_qs, urlsplit

from py_qgis_cache import CacheManager


def test_postgres_storage(data, config):

    cm = CacheManager(config)

    url = cm.resolve_path('/database/project.qgs')
    assert url.scheme == "postgresql"

    # Test resolver
    handler = cm.get_protocol_handler('postgresql')
    resolved_uri = handler.resolve_uri(url)
    print("# resolved_uri:", resolved_uri)

    resolved_url = urlsplit(resolved_uri)
    assert parse_qs(resolved_url.query)['project'][0] == 'project.qgs'

    # Test public path
    rooturl = cm.conf.search_paths['/database']
    public_path = handler.public_path(resolved_uri, '/foobar/baz', rooturl)
    print("# public_path:", public_path)
    assert public_path == '/foobar/baz/project.qgs'
