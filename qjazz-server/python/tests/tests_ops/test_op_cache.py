
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from qjazz_cache.prelude import CacheManager
from qjazz_rpc import messages, op_cache
from qjazz_rpc.config import QgisConfig
from qjazz_rpc.worker import Feedback, Server

from .connection import Connection, NoDataResponse


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
    op_cache.send_cache_list(conn, cm, cache_id=name)

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
    op_cache.send_cache_list(conn, cm, cache_id=name)

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


def test_op_cache_checkout_not_pull(qgis_server: Server, feedback: Feedback, qgis_config: QgisConfig):

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
