import asyncio  # noqa

from contextlib import asynccontextmanager
from time import time

import pytest

from py_qgis_rpc.process import messages
from py_qgis_rpc.worker import Worker, NoDataResponse
from py_qgis_rpc.config import ProjectsConfig, QgisConfig, WorkerConfig

pytest_plugins = ('pytest_asyncio',)


@asynccontextmanager
async def worker_context(projects: ProjectsConfig):
    worker = Worker(WorkerConfig(name="Test", config=QgisConfig(projects=projects)))
    await worker.start()
    try:
        yield worker
    finally:
        print("Sending Quit message")
        await worker.quit()
        assert not worker.is_alive


async def test_worker_io(projects: ProjectsConfig):
    """ Test worker process
    """
    async with worker_context(projects) as worker:

        # Test ping message
        status, _ = await worker.io.send_message(messages.PingMsg())
        assert status == 200

        # Test ping message as dict
        status, resp = await worker.io.send_message(
            {'msg_id': messages.MsgType.PING, 'echo': "hello"},
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
                debug_report=True,
            ),
        )

        print("test_worker_io::status", status)

        assert status == 200
        assert resp.status_code == 200

        print(f"> {resp.headers}")

        # Stream remaining bytes
        async for chunk in worker.io.stream_bytes():
            assert len(chunk) > 0

        # Get final report
        report = await worker.io.read_report()
        print(f"> {report.memory}")
        print(f"> {report.timestamp}")
        print(f"> {report.duration}")


async def test_chunked_response(projects: ProjectsConfig):
    """ Test Response with chunk
    """
    async with worker_context(projects) as worker:

        status, _ = await worker.io.send_message(messages.PingMsg())
        assert status == 200

        start = time()
        # Test Qgis server OWS request with valid project
        status, resp = await worker.io.send_message(
            messages.OwsRequestMsg(
                service="WFS",
                request="GetFeature",
                version="1.0.0",
                options="TYPENAME=france_parts_bordure",
                target="/france/france_parts",
                url="http://localhost:8080/test.3liz.com",
                debug_report=True,
            ),
        )

        total_time = time() - start
        print("> time", total_time)
        assert status == 200
        assert resp.status_code == 200

        print("> headers", resp.headers)

        # Stream remaining bytes
        async for chunk in worker.io.stream_bytes():
            assert len(chunk) > 0

        # Get final report
        report = await worker.io.read_report()
        print("> memory   ", report.memory)
        print("> timestamp", report.timestamp)
        print("> duration ", report.duration)
        print("> overhead:", total_time - report.duration)


async def test_cache_api(projects: ProjectsConfig):
    """ Test worker cache api
    """
    async with worker_context(projects) as worker:

        # Pull
        status, resp = await worker.io.send_message(
            messages.CheckoutProjectMsg(uri="/france/france_parts", pull=True),
        )
        print("\ntest_cache_api::", resp)
        assert status == 200
        assert resp.status == messages.CheckoutStatus.NEW.value
        assert resp.pinned

        uri = resp.uri

        # Checkout
        status, resp = await worker.io.send_message(
            messages.CheckoutProjectMsg(uri="/france/france_parts", pull=False),
        )
        assert status == 200
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


async def test_catalog(projects: ProjectsConfig):
    """ Test worker cache api
    """
    async with worker_context(projects) as worker:

        await worker.io.put_message(messages.CatalogMsg(location="/france"))
        status, item = await worker.io.read_message()
        count = 0
        try:
            while status == 206:
                count += 1
                print("ITEM", item.uri)
                status, item = await worker.io.read_message()
        except NoDataResponse:
            pass

        assert count == 3


async def test_ows_request(projects: ProjectsConfig):
    """ Test worker process
    """
    async with worker_context(projects) as worker:

        echo = await worker.ping("hello")
        assert echo == "hello"

        # Test Qgis server OWS request with valid project
        resp, stream = await worker.ows_request(
            service="WFS",
            request="GetCapabilities",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
        )

        assert resp.status_code == 200
        print(f"> {resp.headers}")

        # Stream data
        async for chunk in stream:
            assert len(chunk) > 0


async def test_ows_chunked_request(projects: ProjectsConfig):
    """ Test worker process
    """
    async with worker_context(projects) as worker:

        echo = await worker.ping("hello")
        assert echo == "hello"

        # Test Qgis server OWS request with valid project
        resp, stream = await worker.ows_request(
            service="WFS",
            request="GetFeature",
            version="1.0.0",
            options="TYPENAME=france_parts_bordure",
            target="/france/france_parts",
            url="http://localhost:8080/test.3liz.com",
        )

        assert resp.status_code == 200
        print(f"> {resp.headers}")

        # Stream remaining bytes
        async for chunk in stream:
            assert len(chunk) > 0

        # Ensure that there is nothing left to read
        async with asyncio.timeout(1):
            await worker.wait_ready()


async def test_api_request(projects: ProjectsConfig):
    """ Test worker process
    """
    async with worker_context(projects) as worker:

        echo = await worker.ping("hello")
        assert echo == "hello"

        # Test Qgis server API request with valid project
        resp, stream = await worker.api_request(
            name="WFS3",
            path="/wfs3/collections",
            target="/france/france_parts",
            url="http://localhost:8080/features",
        )

        assert resp.status_code == 200
        print(f"> {resp.headers}")

        # Stream remaining bytes
        count = 0
        async for chunk in stream:
            count += 1
            assert len(chunk) > 0

        print(f"> chunks: {count}")
