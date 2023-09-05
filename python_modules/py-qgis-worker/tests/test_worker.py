import pytest  # noqa
import asyncio  # noqa

from py_qgis_worker import (
    messages,
    Worker,
    WorkerConfig,
)

from py_qgis_project_cache import ProjectsConfig


pytest_plugins = ('pytest_asyncio',)


async def test_worker_process(data):
    """ Test worker process
    """
    config = WorkerConfig(
        name="Test",
        projects=ProjectsConfig(
            search_paths={
                '/tests': f'{data}/samples/',
                '/france': f'{data}/france_parts/',
                '/montpellier': f'{data}/montpellier/',
            },
        ),
    )

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
