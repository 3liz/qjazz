import shutil

from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest

from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
    ProjectsConfig,
)
from qjazz_rpc import messages, op_cache
from qjazz_rpc.config import QgisConfig
from qjazz_rpc.worker import Feedback, Server

from .connection import Connection, NoDataResponse

Co = messages.CheckoutStatus


class CancelledConnection(Connection):
    """A connection reporting itself as cancelled

    Unlike `Connection.cancel()`, writes are still recorded so that
    we may check what has been sent before the cancellation was seen.
    """

    @property
    def cancelled(self) -> bool:
        return True


def cache_info(conn: Connection, expected_status: int = 200) -> messages.CacheInfo:
    """Read a `CacheInfo` reply"""
    status, resp = conn.read_message()
    assert status == expected_status, resp
    return messages.CacheInfo.model_validate(resp)


def load_unpinned(cm: CacheManager, uri: str) -> CacheEntry:
    """Load a project in cache *without* pinning it

    This is what a plain OWS/API request does, as opposed to an
    explicit checkout with `pull`.
    """
    md, status = cm.checkout(cm.resolve_path(uri))
    entry, _ = cm.update(cast("ProjectMetadata", md), status)
    assert not entry.pinned
    return entry


def copy_project(dest: Path, name: str = "project_simple.qgs") -> Path:
    """Copy a sample project so that it may be modified/removed

    The layers are referenced relatively to the project, so they
    are copied along.
    """
    samples = Path(__file__).parents[1].joinpath("data", "samples")
    for source in (samples.joinpath(name), *samples.glob("*.geojson")):
        shutil.copyfile(source, dest.joinpath(source.name))
    return dest.joinpath(name)


def test_op_cache_checkout_pull(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    name = "test"

    # Test Qgis server OWS request with valid project
    op_cache.checkout_project(
        conn,
        cm,
        qgis_config,
        uri="/france/france_parts",
        pull=True,
        cache_id=name,
    )

    status, resp = conn.read_message()

    print("\ntest_op_cache::checkout::", resp)
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NEW.value
    assert resp.storage == "file"
    assert resp.in_cache
    assert resp.pinned

    # Checkout
    conn.clear()
    op_cache.checkout_project(
        conn,
        cm,
        qgis_config,
        uri="/france/france_parts",
        pull=False,
        cache_id=name,
    )

    status, resp = conn.read_message()
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.UNCHANGED.value

    # Checkout after update
    conn.clear()

    path = Path(urlsplit(resp.uri).path)
    assert path.exists()

    path.touch()

    op_cache.checkout_project(
        conn,
        cm,
        qgis_config,
        uri="/france/france_parts",
        pull=False,
        cache_id=name,
    )

    status, resp = conn.read_message()
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NEEDUPDATE.value

    # List
    conn.clear()
    op_cache.send_cache_list(conn, cm, messages.ListCacheMsg(), cache_id=name)

    status, resp = conn.read_message()
    assert status == 206

    with pytest.raises(NoDataResponse):
        status, _ = conn.read_next_message()

    # Project info
    conn.clear()
    op_cache.send_project_info(conn, cm, "/france/france_parts", cache_id=name)
    status, resp = conn.read_message()
    assert status == 200

    messages.ProjectInfo.model_validate(resp)

    # Drop project
    conn.clear()
    op_cache.drop_project(conn, cm, "/france/france_parts", name)
    status, resp = conn.read_message()
    assert status == 200

    # Empty List
    # List
    conn.clear()
    op_cache.send_cache_list(conn, cm, messages.ListCacheMsg(), cache_id=name)

    with pytest.raises(NoDataResponse):
        status, resp = conn.read_message()
        print("test_op_cache_checkout::list::", status, resp)


def test_op_cache_checkout_no_pull(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    name = "test"

    # Test Qgis server OWS request with valid project
    op_cache.checkout_project(
        conn,
        cm,
        qgis_config,
        uri="/france/france_parts",
        pull=False,
        cache_id=name,
    )

    status, resp = conn.read_message()

    print("\ntest_op_cache::checkout::not_pull::", resp)
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NEW.value
    # Project should have not been loaded
    assert not resp.pinned


def test_op_cache_drop_not_found(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    name = "test"

    # Test Qgis server OWS request with valid project
    op_cache.drop_project(
        conn,
        cm,
        uri="/i_do_not_exists",
        cache_id=name,
    )

    status, resp = conn.read_message()
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NOTFOUND.value
    assert not resp.in_cache


def test_op_cache_checkout_not_found(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    name = "test"

    # Test Qgis server OWS request with valid project
    op_cache.checkout_project(
        conn,
        cm,
        qgis_config,
        uri="/i_do_not_exists",
        pull=False,
        cache_id=name,
    )

    status, resp = conn.read_message()

    print("\ntest_op_cache::not_found::", resp)
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NOTFOUND.value


def test_op_cache_catalog(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    # Test Qgis server OWS request with valid project
    op_cache.send_catalog(conn, cm, location=None)

    for item in conn.stream():
        _ = messages.CatalogItem.model_validate(item)


#
# checkout_project: 'pull' variants not exercised above
#


def test_op_cache_checkout_pull_unchanged_and_updated(
    qgis_server: Server,
    qgis_config: QgisConfig,
    tmp_path: Path,
):
    """Pulling an already cached project: UNCHANGED then UPDATED"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    path = copy_project(tmp_path)

    def pull() -> messages.CacheInfo:
        conn.clear()
        op_cache.checkout_project(conn, cm, qgis_config, uri=str(path), pull=True)
        return cache_info(conn)

    assert pull().status == Co.NEW.value

    resp = pull()
    assert resp.status == Co.UNCHANGED.value
    assert resp.pinned
    assert resp.hits == 0

    # Pulling an outdated project reloads it
    path.touch()
    resp = pull()
    assert resp.status == Co.UPDATED.value
    assert resp.in_cache
    assert resp.pinned


def test_op_cache_checkout_removed(
    qgis_server: Server,
    qgis_config: QgisConfig,
    tmp_path: Path,
):
    """A cached project whose storage disappeared is reported as REMOVED"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    path = copy_project(tmp_path)

    op_cache.checkout_project(conn, cm, qgis_config, uri=str(path), pull=True)
    assert cache_info(conn).status == Co.NEW.value

    path.unlink()

    # Without pull the entry is still held in cache
    conn.clear()
    op_cache.checkout_project(conn, cm, qgis_config, uri=str(path), pull=False)
    resp = cache_info(conn)
    assert resp.status == Co.REMOVED.value
    assert resp.in_cache
    assert len(cm) == 1

    # Pulling evicts it
    conn.clear()
    op_cache.checkout_project(conn, cm, qgis_config, uri=str(path), pull=True)
    resp = cache_info(conn)
    assert resp.status == Co.REMOVED.value
    assert not resp.in_cache
    assert len(cm) == 0


def test_op_cache_checkout_pull_not_found(qgis_server: Server, qgis_config: QgisConfig):
    """NOTFOUND is handled by the 'pull' branch as well"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    op_cache.checkout_project(conn, cm, qgis_config, uri="/i_do_not_exists", pull=True)

    resp = cache_info(conn)
    assert resp.status == Co.NOTFOUND.value
    assert not resp.in_cache
    # The reply holds the resolved url
    assert resp.uri.endswith("/i_do_not_exists")


#
# checkout_project: errors
#


def test_op_cache_checkout_resource_not_allowed(qgis_server: Server, qgis_config: QgisConfig):
    """A relative path is rejected by the file handler"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    op_cache.checkout_project(conn, cm, qgis_config, uri="not/absolute", pull=False)

    status, _ = conn.read_message()
    assert status == 403

    conn.clear()
    op_cache.send_project_info(conn, cm, "not/absolute")
    status, _ = conn.read_message()
    assert status == 403


def test_op_cache_checkout_strict_checking_failure(qgis_server: Server, qgis_config: QgisConfig):
    """Loading a project with bad layers fails with strict checking on"""
    cm = CacheManager.get_service()
    cm.clear()

    assert not cm.conf.ignore_bad_layers

    conn = Connection()
    op_cache.checkout_project(conn, cm, qgis_config, uri="/tests/bad_layer", pull=True)

    status, _ = conn.read_message()
    assert status == 500
    assert len(cm) == 0


#
# Cache eviction
#


def test_op_cache_checkout_evict_unpinned(
    qgis_server: Server,
    qgis_config: QgisConfig,
    tmp_path: Path,
):
    """Reaching `max_projects` evicts the least popular unpinned project"""
    cm = CacheManager.get_service()
    cm.clear()

    load_unpinned(cm, "/france/france_parts")

    config = qgis_config.model_copy(update={"max_projects": 1})

    conn = Connection()
    path = copy_project(tmp_path)
    op_cache.checkout_project(conn, cm, config, uri=str(path), pull=True)

    resp = cache_info(conn)
    assert resp.status == Co.NEW.value
    assert resp.pinned
    # The unpinned entry has been evicted in favour of the new one
    assert len(cm) == 1
    assert [e.md.uri for e in cm.iter()] == [str(path)]


def test_op_cache_checkout_max_projects_reached(
    qgis_server: Server,
    qgis_config: QgisConfig,
    tmp_path: Path,
):
    """Nothing may be evicted when every cached project is pinned"""
    cm = CacheManager.get_service()
    cm.clear()

    config = qgis_config.model_copy(update={"max_projects": 1})

    conn = Connection()
    op_cache.checkout_project(conn, cm, config, uri="/france/france_parts", pull=True)
    assert cache_info(conn).pinned

    assert not op_cache.evict_project_from_cache(cm)

    conn.clear()
    op_cache.checkout_project(conn, cm, config, uri=str(copy_project(tmp_path)), pull=True)
    status, _ = conn.read_message()
    assert status == 403
    assert len(cm) == 1


#
# send_cache_list filters
#


def test_op_cache_list_filters(qgis_server: Server, qgis_config: QgisConfig, tmp_path: Path):
    """`pinned_filter` and `status_filter` select the streamed entries"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()

    # One pinned entry
    pinned = copy_project(tmp_path)
    op_cache.checkout_project(conn, cm, qgis_config, uri=str(pinned), pull=True)
    assert cache_info(conn).pinned

    # One unpinned entry
    unpinned = load_unpinned(cm, "/france/france_parts")
    assert len(cm) == 2

    def cache_list(msg: messages.ListCacheMsg) -> list[messages.CacheInfo]:
        conn.clear()
        op_cache.send_cache_list(conn, cm, msg)
        try:
            return [messages.CacheInfo.model_validate(item) for item in conn.stream()]
        except NoDataResponse:
            return []

    assert len(cache_list(messages.ListCacheMsg())) == 2

    items = cache_list(messages.ListCacheMsg(pinned_filter=True))
    assert [i.uri for i in items] == [str(pinned)]

    # Both entries are UNCHANGED
    assert len(cache_list(messages.ListCacheMsg(status_filter=CheckoutStatus.UNCHANGED))) == 2
    assert cache_list(messages.ListCacheMsg(status_filter=CheckoutStatus.NEEDUPDATE)) == []

    # Filters are combined
    pinned.touch()
    items = cache_list(
        messages.ListCacheMsg(pinned_filter=True, status_filter=CheckoutStatus.NEEDUPDATE),
    )
    assert [i.uri for i in items] == [str(pinned)]
    assert unpinned.md.uri not in (i.uri for i in items)


def test_op_cache_streams_stop_when_cancelled(qgis_server: Server, qgis_config: QgisConfig):
    """A cancelled connection interrupts both streaming operations"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    op_cache.checkout_project(conn, cm, qgis_config, uri="/france/france_parts", pull=True)
    assert cache_info(conn).in_cache

    for operation in (
        lambda c: op_cache.send_cache_list(c, cm, messages.ListCacheMsg()),
        lambda c: op_cache.send_catalog(c, cm, location=None),
    ):
        cancelled = CancelledConnection()
        operation(cancelled)
        # Only the end of transmission marker has been sent
        with pytest.raises(NoDataResponse):
            cancelled.read_message()


#
# send_project_info
#


def test_op_cache_project_info_not_in_cache(qgis_server: Server, qgis_config: QgisConfig):
    """An existing but unloaded project is not available"""
    cm = CacheManager.get_service()
    cm.clear()

    conn = Connection()
    op_cache.send_project_info(conn, cm, "/france/france_parts")

    status, msg = conn.read_message()
    assert status == 404
    assert "france_parts" in msg


def test_op_cache_project_info_bad_layers(qgis_server: Server, projects: ProjectsConfig):
    """`has_bad_layers` is reported when bad layers are tolerated"""
    # A dedicated manager: the shared one runs with strict checking
    cm = CacheManager(projects.model_copy(update={"ignore_bad_layers": True}))

    load_unpinned(cm, "/tests/bad_layer")

    conn = Connection()
    op_cache.send_project_info(conn, cm, "/tests/bad_layer", cache_id="test")

    status_code, resp = conn.read_message()
    assert status_code == 200

    info = messages.ProjectInfo.model_validate(resp)
    assert info.cache_id == "test"
    assert info.storage == "file"
    assert info.filename.endswith("bad_layer.qgs")
    assert info.has_bad_layers
    assert any(not layer.is_valid for layer in info.layers)

    cm.clear()


#
# send_catalog
#


def test_op_cache_catalog_location(qgis_server: Server, qgis_config: QgisConfig):
    """The catalog may be restricted to a single search path"""
    cm = CacheManager.get_service()

    conn = Connection()
    op_cache.send_catalog(conn, cm, location="/france")

    items = [messages.CatalogItem.model_validate(item) for item in conn.stream()]
    assert items
    assert all(i.public_uri.startswith("/france/") for i in items)
    assert all(i.storage == "file" for i in items)


#
# timestamp_to_iso
#


def test_op_cache_timestamp_to_iso():
    assert op_cache.timestamp_to_iso(None) is None
    assert op_cache.timestamp_to_iso(0) is None
    assert op_cache.timestamp_to_iso(1735689600.0).startswith("2025-01-01")
