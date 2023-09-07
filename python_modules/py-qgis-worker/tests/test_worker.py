import pytest  # noqa
import asyncio  # noqa

from time import time
from py_qgis_worker import messages
from py_qgis_worker import messages as _m
from py_qgis_worker.process import Worker

pytest_plugins = ('pytest_asyncio',)


async def test_worker_process(config):
    """ Test worker process
    """
    worker = Worker(config)
    worker.start()

    # Test ping message
    status, _ = await worker.io.send_message(messages.Ping())
    assert status == 200

    # Test Qgis server OWS request with valid project
    status, resp = await worker.io.send_message(
        messages.OWSRequest(
            service="WFS",
            request="GetCapabilities",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
        ),
    )

    assert status == 200
    assert resp.status_code == 200

    print(f"> {resp.chunked}")
    print(f"> {resp.headers}")

    if resp.chunked:
        # Stream remaining bytes
        async for chunk in worker.io.stream_bytes():
            assert len(chunk > 0)

    # Get final report
    report = await worker.io.read()
    print(f"> {report.memory}")
    print(f"> {report.timestamp}")
    print(f"> {report.duration}")

    # Test quit message
    status, _ = await worker.io.send_message(messages.Quit())
    assert status == 200

    worker.join(5)
    assert not worker.is_alive()


async def test_chunked_response(config):
    """ Test worker process
    """
    worker = Worker(config)
    worker.start()

    status, _ = await worker.io.send_message(messages.Ping())
    assert status == 200

    start = time()
    # Test Qgis server OWS request with valid project
    status, resp = await worker.io.send_message(
        messages.OWSRequest(
            service="WFS",
            request="GetFeature",
            version="1.0.0",
            options="TYPENAME=france_parts_bordure",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
        ),
    )

    total_time = time() - start
    print("> ", total_time)
    assert status == 200
    assert resp.status_code == 200

    print("> ", resp.chunked)
    print("> ", resp.headers)

    if resp.chunked:
        # Stream remaining bytes
        async for chunk in worker.io.stream_bytes():
            assert len(chunk) > 0

    # Get final report
    report = await worker.io.read()
    print("> ", report.memory)
    print("> ", report.timestamp)
    print("> ", report.duration)
    print("> overhead:", total_time - report.duration)

    # Test quit message
    status, _ = await worker.io.send_message(messages.Quit())
    assert status == 200

    worker.join(5)
    assert not worker.is_alive()


async def test_worker_api(config):
    """ Test worker api
    """
    worker = Worker(config)
    worker.start()

    # Pull
    status, resp = await worker.io.send_message(
        _m.CheckoutProject(uri="/france/france_parts", pull=True)
    )
    assert status == 200
    assert resp.status == _m.CheckoutStatus.NEW

    uri = resp.uri

    # Checkout
    status, resp = await worker.io.send_message(
        _m.CheckoutProject(uri="/france/france_parts", pull=False)
    )
    assert status == 200
    assert resp.status == _m.CheckoutStatus.UNCHANGED

    # List
    status, resp = await worker.io.send_message(
        _m.ListCache()
    )

    assert status == 200
    assert resp == 1
    status, item = await worker.io.read_message()
    while status == 206:
        status, item = await worker.io.read_message()
    assert status == 200

    status, resp = await worker.io.send_message(
        _m.DropProject(uri)
    )
    assert status == 200

    # Empty List
    status, resp = await worker.io.send_message(
        _m.ListCache()
    )

    assert status == 200
    assert resp == 0
