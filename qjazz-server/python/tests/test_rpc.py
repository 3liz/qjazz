import asyncio  # noqa

from time import time

import pytest

from qjazz_rpc import messages
from qjazz_rpc.tests.worker import Worker, NoDataResponse

pytest_plugins = ("pytest_asyncio",)


async def test_rpc_io(worker: Worker):
    """Test worker process"""
    # Test ping message
    status, _ = await worker.io.send_message(messages.PingMsg())
    assert status == 200

    # Test ping message as dict
    status, resp = await worker.io.send_message(
        {"msg_id": messages.MsgType.PING, "echo": "hello"},
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


async def test_rpc_chunked_response(worker: Worker):
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


async def test_rpc_cache_api(worker: Worker):
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


async def test_rpc_catalog(worker: Worker):
    """Test worker cache api"""
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


async def test_rpc_ows_chunked_request(worker: Worker):
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


async def test_rpc_api_request(worker: Worker):
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


async def test_rpc_api_delegate_request(worker: Worker):
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
