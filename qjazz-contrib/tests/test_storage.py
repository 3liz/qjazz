from urllib.parse import parse_qs, urlsplit

import pytest

from qjazz_cache.prelude import CacheManager, ProjectsConfig, errors


def test_storage_postgres(data, config):
    cm = CacheManager(config)

    url = cm.resolve_path("/database/project.qgs")
    print("test_postgres_storage:", url)
    assert url.scheme == "postgresql"

    # Test resolver
    handler = cm.get_protocol_handler("postgresql")
    resolved_uri = handler.resolve_uri(url)
    print("test_postgres_storage#resolved_uri:", resolved_uri)

    resolved_url = urlsplit(resolved_uri)
    assert parse_qs(resolved_url.query)["project"][0] == "project.qgs"

    # Test public path
    _, rooturl = cm.conf.search_paths._routes["/database"].cannonical
    public_path = handler.public_path(resolved_uri, "/foobar/baz", rooturl)
    print("test_postgres_storage#public_path:", public_path)
    assert public_path == "/foobar/baz/project.qgs"

    # Test path substitution
    url = cm.resolve_path("/mydb/project.qgs")
    print("test_postgres_storage:url", url)
    assert url.scheme == "postgresql"
    resolved_url = urlsplit(resolved_uri)
    assert parse_qs(resolved_url.query)["project"][0] == "project.qgs"


def test_storage_geopackage(data, config):
    conf = ProjectsConfig(
        search_paths={
            "/mygpkg": "geopackage:/do/not/exists.gpkg&projectName={path}",
        },
    )

    with pytest.raises(errors.InvalidCacheRootUrl):
        handler = CacheManager.get_protocol_handler("geopackage")
        handler.validate_rooturl(conf.search_paths._routes["/mygpkg"]._url, config)
