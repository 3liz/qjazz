from pathlib import Path

import pytest

from aiohttp.test_utils import TestClient

from py_qgis_processes.server._handlers import (
    processes,
)


@pytest.mark.services
async def test_server_processes(workdir: Path, http_client: TestClient):

    resp = await http_client.get('/processes')
    assert resp.status == 200

    data = await resp.text()
    print("test_http_processes::", data)

    res = processes.ProcessList.model_validate_json(data)

    assert len(res.processes) > 1
