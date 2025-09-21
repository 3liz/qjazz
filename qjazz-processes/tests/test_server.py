from pathlib import Path

import pytest

from aiohttp.test_utils import TestClient

from qjazz_processes.schemas import (
    JobStatus,
    ProcessDescription,
)
from qjazz_processes.server._handlers import (
    jobs,
    processes,
)


@pytest.mark.services
async def test_server_processes(workdir: Path, http_client: TestClient):
    # Test process list

    resp = await http_client.get("/processes/")
    assert resp.status == 200

    data = await resp.text()
    print("test_service_processes::", data)

    res = processes.ProcessList.model_validate_json(data)

    assert len(res.processes) > 1

    #
    # Test describe
    #

    resp = await http_client.get(
        "/processes/model:centroides?service=Test&map=/france/france_parts",
    )
    assert resp.status == 200

    data = await resp.text()
    print("test_server_describe::", data)

    res = ProcessDescription.model_validate_json(data)

    #
    # Test execute
    #

    resp = await http_client.post(
        "/processes/model:centroides/execution?service=Test&map=/france/france_parts",
        json={
            "inputs": {
                "input": "france_parts",
                "native:centroids_1:OUTPUT": "output_layer",
            },
        },
    )
    assert resp.status == 201

    data = await resp.text()
    print("test_server_execution::", data)

    jobstatus = JobStatus.model_validate_json(data)
    print("test_server_execution::status", jobstatus.status)

    #
    # Test jobs
    #

    resp = await http_client.get("/jobs/")
    assert resp.status == 200

    data = await resp.text()
    print("test_server_jobs::", data)

    joblist = jobs.JobList.model_validate_json(data)
    assert len(joblist.jobs) >= 1
