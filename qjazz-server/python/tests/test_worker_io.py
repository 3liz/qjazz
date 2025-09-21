import asyncio
import json

from pathlib import PurePosixPath
from time import time

import pytest

from qjazz_ogc import OgcEndpoints
from qjazz_ogc.stac import CatalogBase

from qjazz_rpc import messages
from qjazz_rpc.tests.worker import NoDataResponse, Worker

pytest_plugins = ("pytest_asyncio",)


async def test_worker_io_ping(worker: Worker):
    """Test worker process"""
    # Test ping message
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    # Test ping message as dict
    status, resp = await worker.io.send_message(
        {"msg_id": messages.MsgType.PING, "echo": "hello"},   # type: ignore [arg-type]
    )
    assert status == 200
    assert resp == "hello"

    # Test Qgis server OWS request with valid project
    status, resp = await worker.io.send_message(
        messages.OwsRequestMsg(
            service="WFS",
            request="GetCapabilities",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
            header_prefix="x-test-",
        ),
    )

    print("test_worker_io::status", status)

    assert status == 200

    resp = messages.RequestReply.model_validate(resp)

    assert resp.status_code == 200
    assert resp.target == "/france/france_parts"

    print(f"> {resp.headers}")

    # Check header prefix
    for k, _ in resp.headers:
        assert k.startswith("x-test-")

    # Stream remaining bytes
    async for chunk in worker.io.stream_bytes():
        assert len(chunk) > 0


async def test_worker_io_chunked_response(worker: Worker):
    """Test Response with chunk"""
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    start = time()
    # Test Qgis server OWS request with valid project
    status, resp = await worker.io.send_message(
        messages.OwsRequestMsg(
            service="WFS",
            request="GetFeature",
            version="1.0.0",
            options="SERVICE=WFS&REQUEST=GetFeature&TYPENAME=france_parts_bordure",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
        ),
    )

    total_time = time() - start
    print("> time", total_time)
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200

    print("> headers", resp.headers)

    # Stream remaining bytes
    async for chunk in worker.io.stream_bytes():
        assert len(chunk) > 0


async def test_worker_io_cache_api(worker: Worker):
    """Test worker cache api"""
    # Pull
    status, resp = await worker.io.send_message(
        messages.CheckoutProjectMsg(uri="/france/france_parts", pull=True),
    )
    print("\ntest_cache_api::", resp)
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.NEW.value
    assert resp.pinned

    uri = resp.uri

    # Checkout
    status, resp = await worker.io.send_message(
        messages.CheckoutProjectMsg(uri="/france/france_parts", pull=False),
    )
    assert status == 200

    resp = messages.CacheInfo.model_validate(resp)
    assert resp.status == messages.CheckoutStatus.UNCHANGED.value

    # List
    await worker.io.put_message(messages.ListCacheMsg())
    status, _ = await worker.io.read_message()
    assert status == 206

    with pytest.raises(NoDataResponse):
        status, _ = await worker.io.read_message()

    # Project info
    status, resp = await worker.io.send_message(
        messages.GetProjectInfoMsg(uri="/france/france_parts"),
    )
    assert status == 200

    # Drop project
    status, resp = await worker.io.send_message(
        messages.DropProjectMsg(uri=uri),
    )
    assert status == 200

    # Empty List
    await worker.io.put_message(messages.ListCacheMsg())
    with pytest.raises(NoDataResponse):
        _ = await worker.io.read_message()


async def test_worker_io_catalog(worker: Worker):
    """Test worker catalog api"""
    await worker.io.put_message(messages.CatalogMsg(location="/france"))
    status, item = await worker.io.read_message()
    count = 0
    try:
        while status == 206:
            count += 1
            item = messages.CatalogItem.model_validate(item)
            print("ITEM", item.uri)
            status, item = await worker.io.read_message()
    except NoDataResponse:
        pass

    assert count == 3


async def test_worker_io_ows_chunked_request(worker: Worker):
    """Test worker process"""
    # Test ping message
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    # Test Qgis server OWS request with valid project
    status, resp = await worker.io.send_message(
        messages.OwsRequestMsg(
            service="WFS",
            request="GetFeature",
            version="1.0.0",
            options="SERVICE=WFS&REQUEST=GetFeature&TYPENAME=france_parts_bordure",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
            send_report=True,
        ),
    )
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200
    print(f"> {resp.headers}")

    # Stream remaining bytes
    async for chunk in worker.io.stream_bytes():
        assert len(chunk) > 0

    # Read report
    status, report = await worker.io.read_message()
    print(f"> REPORT: {report}")
    assert status == 200

    # Ensure that there is nothing left to read
    async with asyncio.timeout(1):
        await worker.wait_ready()


async def test_worker_io_api_request(worker: Worker):
    """Test worker process"""
    # Test ping message
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    # Test Qgis server API request with valid project
    status, resp = await worker.io.send_message(
        messages.ApiRequestMsg(
            name="WFS3",
            path="/wfs3/collections",
            target="/france/france_parts",
            url="http://localhost:8080/features",
            method=messages.HTTPMethod.GET,
            delegate=True,
        ),
    )
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200
    print(f"> {resp.headers}")

    # Stream remaining bytes
    count = 0
    async for chunk in worker.io.stream_bytes():
        count += 1
        assert len(chunk) > 0

    print(f"> chunks: {count}")


async def test_worker_io_api_delegate_request(worker: Worker):
    """Test worker process"""
    # Test ping message
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    # Test Qgis server API request with valid project
    status, resp = await worker.io.send_message(
        messages.ApiRequestMsg(
            name="WFS3",
            path="",
            target="/france/france_parts",
            url="http://localhost:8080/features",
            delegate=True,
            method=messages.HTTPMethod.GET,
        ),
    )
    assert status == 200

    resp = messages.RequestReply.model_validate(resp)
    assert resp.status_code == 200
    print(f"> {resp.headers}")

    # Stream remaining bytes
    count = 0
    async for chunk in worker.io.stream_bytes():
        count += 1
        assert len(chunk) > 0

    print(f"> chunks: {count}")


async def test_ogc_catalog_api(worker: Worker):
    """Test worker catalog api"""
    await worker.io.put_message(
        messages.CollectionsMsg(
            start=0,
            end=50,
        ),
    )

    status, resp = await worker.io.read_message()
    print("\n::test_ogc_api::catalog", status)
    assert status == 200

    resp = messages.CollectionsPage.model_validate(resp)

    assert not resp.next
    assert len(resp.items) > 0
    assert len(resp.items) < 50

    schema = json.loads(resp.schema_)
    print("\n::test_ogc_api::catalog::schema\n", schema)

    print("\n::test_ogc_api::catalog::items:")
    print("\n".join(n.name for n in resp.items))

    item = resp.items[0]
    print("\n::test_ogc_api::catalog::item", item)

    coll = CatalogBase.model_validate_json(item.json_)

    assert coll.id == item.name
    assert item.endpoints == OgcEndpoints.MAP.value


async def test_ogc_catalog_prefix(worker: Worker):
    """Test worker catatalog api"""

    prefix = "/france/"

    await worker.io.put_message(
        messages.CollectionsMsg(
            start=0,
            end=50,
            location=prefix,
        ),
    )

    status, resp = await worker.io.read_message()
    print("\n::test_ogc_api::catalog_prefix", status)
    assert status == 200

    resp = messages.CollectionsPage.model_validate(resp)

    assert len(resp.items) > 0
    for item in resp.items:
        print("\n::test_ogc_api::catalog_prefix::item", item)
        assert PurePosixPath(item.name).is_relative_to(prefix)


