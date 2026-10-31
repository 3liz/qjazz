#
# Test that the async executor does not block the event loop
#
import asyncio
import time

from types import SimpleNamespace
from typing import cast

from qjazz_processes.executor.executor import AsyncExecutor
from qjazz_processes.schemas import JobExecute


async def test_executor_execute_does_not_block_event_loop():
    def _execute(service, ident, request, **kwargs):
        # Blocking calls to the backend and the broker
        time.sleep(0.3)
        return "job_01", lambda timeout: {}, lambda: None

    executor = cast("AsyncExecutor", SimpleNamespace(_execute=_execute))

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        result = await AsyncExecutor.execute(executor, "test", "process", JobExecute(inputs={}))
    finally:
        task.cancel()

    assert result.job_id == "job_01"
    # The event loop kept running while the job was sent
    assert ticks >= 10
