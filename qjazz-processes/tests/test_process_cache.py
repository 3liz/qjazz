#
# Test process cache request/response exchanges (M11)
#
import multiprocessing as mp
import threading
import time

from typing import Any, Iterator, Optional, cast

import pytest

from qjazz_processes.processing.config import ProcessingConfig
from qjazz_processes.schemas import ProcessDescription, ProcessSummary
from qjazz_processes.worker import cache
from qjazz_processes.worker.cache import ProcessCache

# Description requests for this project take longer than the poll timeout
SLOW_PROJECT = "slow"
SLOW_DELAY = 1.0


class FakeCache(ProcessCache):
    """Process cache without QGIS"""

    def initialize(self):
        pass

    def _update(self) -> list[ProcessSummary]:
        return [ProcessSummary.model_validate({"id": "alg", "title": "Algorithm", "version": "1.0"})]

    def _describe(self, ident: str, project: Optional[str]) -> ProcessDescription:
        if project == SLOW_PROJECT:
            time.sleep(SLOW_DELAY)
        return ProcessDescription.model_validate(
            {
                "id": ident,
                "title": f"{ident}@{project}",
                "version": "1.0",
                "inputs": {},
                "outputs": {},
            },
        )


@pytest.fixture()
def process_cache(processing_config: ProcessingConfig) -> Iterator[FakeCache]:
    proc = FakeCache(processing_config)
    proc.start()
    proc.update()
    yield proc
    proc.stop()


def test_process_cache_late_response(process_cache: FakeCache, monkeypatch: pytest.MonkeyPatch):
    """A late response is not taken as the response of the next request"""
    monkeypatch.setattr(cache, "POLL_TIMEOUT", 0.2)

    with pytest.raises(RuntimeError):
        process_cache.describe("alg", SLOW_PROJECT)

    # Let the late response arrive in the pipe
    time.sleep(SLOW_DELAY + 0.2)

    processes = process_cache.update()
    assert [p.id_ for p in processes] == ["alg"]

    description = process_cache.describe("alg", "fast")
    assert description is not None
    assert description["title"] == "alg@fast"


def test_process_cache_concurrent_requests(process_cache: FakeCache):
    """Requests from multiple threads get their own response

    Without serialized exchanges, two threads may wait on the pipe
    at the same time and one of them may block forever in `recv()`:
    requests run in daemon threads so that a blocked thread
    fails the test instead of hanging it.
    """
    descriptions: dict[int, str] = {}
    updates: list[list[str]] = []
    errors: list[Exception] = []

    def _requests(n: int) -> None:
        try:
            for i in range(n * 10, (n + 1) * 10):
                description = process_cache.describe("alg", f"project_{i}")
                assert description is not None
                descriptions[i] = cast("str", description["title"])
                updates.append([p.id_ for p in process_cache.update()])
        except Exception as err:
            errors.append(err)

    threads = [threading.Thread(target=_requests, args=(n,), daemon=True) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "Requests are blocked (deadlock)"
    assert errors == []
    assert descriptions == {i: f"alg@project_{i}" for i in range(80)}
    assert len(updates) == 80
    assert all(ids == ["alg"] for ids in updates)


@pytest.mark.parametrize("start_method", ["fork", "forkserver", "spawn"])
def test_process_cache_start_method(
    processing_config: ProcessingConfig,
    start_method: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """The process cache can be started with any start method

    'spawn' and 'forkserver' require the process object to be picklable.
    """
    # Use the start method for this process only
    context = cast("Any", mp.get_context(start_method))
    monkeypatch.setattr(FakeCache, "_Popen", staticmethod(context.Process._Popen))

    proc = FakeCache(processing_config)
    proc.start()
    try:
        assert [p.id_ for p in proc.update()] == ["alg"]
        description = proc.describe("alg", start_method)
        assert description is not None
        assert description["title"] == f"alg@{start_method}"
    finally:
        proc.stop()

    assert proc.exitcode == 0
