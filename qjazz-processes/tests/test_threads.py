#
# Test worker periodic tasks
#
import time

from qjazz_processes.worker.threads import PeriodicTasks


def test_periodic_tasks_shutdown_not_started():
    """Shutdown before start (i.e worker stopped before being ready)"""
    tasks = PeriodicTasks()
    tasks.add("task1", lambda: None, 0.01)
    tasks.add("task2", lambda: None, 0.01)

    tasks.shutdown()


def test_periodic_tasks_shutdown_started():
    """Started tasks are stopped and joined"""
    calls = 0

    def target():
        nonlocal calls
        calls += 1

    tasks = PeriodicTasks()
    tasks.add("task", target, 0.01)
    tasks.start()

    deadline = time.monotonic() + 5.0
    while calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert calls > 0

    tasks.shutdown()

    assert not any(task.is_alive() for task in tasks._periodic_tasks)
