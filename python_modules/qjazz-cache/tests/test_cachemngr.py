from pathlib import Path

import pytest

from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
)
from qjazz_cache.errors import StrictCheckingFailure
from qjazz_contrib.core import logger


def test_path_resolution(data, config):

    cm = CacheManager(config)

    uri = cm.resolve_path('/tests/project_simple')
    assert uri.scheme == 'file', f"Expecting 'file' scheme, found '{uri.scheme}'"
    assert uri.path == f'{data.joinpath("samples/project_simple")}'


def test_collect_projects(data, config):

    cm = CacheManager(config)

    collected = list(cm.collect_projects())
    logger.debug(collected)
    assert len(collected) > 0
    for md, _ in collected:
        match md.scheme:
            case 'file':
                path = Path(md.uri)
                assert md.storage == 'file'
                assert md.name == path.stem
                assert path.is_relative_to(data)
            case _:
                pytest.fail(reason=f"unexpected scheme: '{md.scheme}'")


def test_collect_projects_from_search_path(data, config):

    cm = CacheManager(config)

    collected = list(cm.collect_projects('/france'))
    assert len(collected) > 0
    print('\n')
    for md, public_path in collected:
        print("#", md, public_path)
        assert public_path.startswith('/france')


def test_checkout_project(config):

    cm = CacheManager(config)

    url = cm.resolve_path('/france/france_parts.qgs')

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.NEW
    assert isinstance(md, ProjectMetadata)

    entry, _ = cm.update(md, status)
    assert isinstance(entry, CacheEntry)

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.UNCHANGED


def test_checkout_invalid_layers(config):

    cm = CacheManager(config)

    url = cm.resolve_path('/tests/project_simple_with_invalid.qgs')

    md, status = cm.checkout(url)
    assert status == CheckoutStatus.NEW
    assert isinstance(md, ProjectMetadata)

    with pytest.raises(StrictCheckingFailure):
        _ = cm.update(md, status)


