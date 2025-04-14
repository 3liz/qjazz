
from pathlib import Path, PurePosixPath

def test_dynamic_route_impl():
    from qjazz_cache.routes import Routes, urlsplit

    routes = Routes({
        "/foo/bar": "/myfoo/mybar",
        "/baz/{Loc1}/{Loc2}": "/mybaz/{Loc1}/myloc/{Loc2}",
    })

    locs = list(routes.locations("/foo"))
    assert len(locs) == 1
    assert locs[0] == ("/foo/bar", urlsplit("file:/myfoo/mybar"))

    # Check substitution
    locs = list(routes.locations("/baz/loc1/loc2"))
    assert len(locs) == 1
    assert locs[0] == ("/baz/loc1/loc2", urlsplit("file:/mybaz/loc1/myloc/loc2"))

    # Should return only static routes
    locs = list(routes.locations())
    assert len(locs) == 1
    assert locs[0][0] == "/foo/bar"

    # Path resolution:w
    for route in routes.routes:
        result = route.resolve_path(PurePosixPath("/baz/path1/path2/myproject.qgs"))
        if result:
            break

    assert result

    location, url = result
    assert location == "/baz/path1/path2"
    assert url == urlsplit("file:/mybaz/path1/myloc/path2")


def test_dynamic_config(data: Path):
    from qjazz_cache.prelude import CacheManager, ProjectsConfig

    conf = ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=True,
        force_readonly_layers=True,
        search_paths={
            "/france": f"{data}/france_parts/",
            "/dyn/{loc}":  f"{data}/{{loc}}"
        },
    )

    cm = CacheManager(conf)

    uri = cm.resolve_path("/dyn/montpellier/montpellier.qgs")
    assert uri.scheme == "file"
    assert uri.path == f"{data.joinpath('montpellier/montpellier.qgs')}"

