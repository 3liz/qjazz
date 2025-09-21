import contextlib

from pathlib import Path

import pytest

from qjazz_cache.errors import ResourceNotAllowed, StrictCheckingFailure
from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
    ProjectsConfig,
    ResourceStore,
)
from qjazz_cache.routes import DynamicRoute, StaticRoute
from qjazz_core import logger


def test_search_paths(config: ProjectsConfig):
    sp = config.search_paths
    for route in sp._routes.values():
        assert isinstance(route, (StaticRoute, DynamicRoute))

        _, url = route.cannonical
        assert url.scheme, "Expecting scheme"


def test_path_resolution(data: Path, config: ProjectsConfig):
    cm = CacheManager(config)

    uri = cm.resolve_path("/tests/project_simple")
    assert uri.scheme == "file", f"Expecting 'file' scheme, found '{uri.scheme}'"
    assert uri.path == f"{data.joinpath('samples/project_simple')}"


def test_collect_projects(data: Path, config: ProjectsConfig):
    cm = CacheManager(config)

    collected = list(cm.collect_projects())
    logger.debug(collected)
    assert len(collected) > 0
    for md, _ in collected:
        match md.scheme:
            case "file":
                path = Path(md.uri)
                assert md.storage == "file"
                assert md.name == path.stem
                assert path.is_relative_to(data)
            case _:
                pytest.fail(reason=f"unexpected scheme: '{md.scheme}'")


def test_collect_projects_from_search_path(data: Path, config: ProjectsConfig):
    cm = CacheManager(config)

    collected = list(cm.collect_projects("/france"))
    assert len(collected) > 0
    print("\n")
    for md, public_path in collected:
        print("#", md, public_path)
        assert public_path.startswith("/france")


def test_checkout_project(config: ProjectsConfig):
    cm = CacheManager(config)

    url = cm.resolve_path("/france/france_parts.qgs")

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.NEW
    assert isinstance(md, ProjectMetadata)

    entry, _ = cm.update(md, status)
    assert isinstance(entry, CacheEntry)

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.UNCHANGED


def test_checkout_invalid_layers(config: ProjectsConfig):
    cm = CacheManager(config)

    url = cm.resolve_path("/tests/project_simple_with_invalid.qgs")

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.NEW
    assert isinstance(md, ProjectMetadata)

    with pytest.raises(StrictCheckingFailure):
        _ = cm.update(md, status)


def test_resource_stream(config: ProjectsConfig):
    cm = CacheManager(config)

    url = cm.resolve_path("/montpellier/montpellier.qgs.png")
    print("\n::test_resource_stream::url", url)

    handler = cm.get_protocol_handler(url.scheme)
    assert isinstance(handler, ResourceStore)

    res = handler.get_resource(url)
    print("::test_resource_stream::res", res)
    assert res is not None
    assert res.size > 0

    with contextlib.closing(res) as res:
        b = res.read(50)
        assert len(b) == 50

    url = cm.resolve_path("/montpellier/i_do_not_exists")
    print("\n::test_resource_stream::url", url)

    handler = cm.get_protocol_handler(url.scheme)
    assert isinstance(handler, ResourceStore)
    assert handler.get_resource(url) is None


def test_invalid_path(config: ProjectsConfig):
    cm = CacheManager(config)

    with pytest.raises(ResourceNotAllowed):
        url = cm.resolve_path("/i_do_not_exists")
        print("\n::test_resource_stream::url", url)


