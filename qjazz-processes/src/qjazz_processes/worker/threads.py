import traceback

from threading import Event, Thread
from typing import Callable

from qjazz_core import logger


#
# Define threaded wrapper for periodic task
#
class PeriodicTask(Thread):
    def __init__(
        self,
        name: str,
        target: Callable[[], None],
        timeout: float,
        *,
        event: Event,
    ):
        super().__init__(name=name)
        self._target = target
        self._event = event
        self._timeout = timeout

    def run(self):
        logger.info("Started task '%s'", self.name)
        while not self._event.wait(self._timeout):
            try:
                self._target()
            except Exception as err:
                logger.error(f"Task {self.name} failed: {err}")
                traceback.print_exc()
        logger.info("Stopped task '%s'", self.name)


class PeriodicTasks:
    def __init__(self) -> None:
        self._shutdown_event = Event()
        self._periodic_tasks: list[PeriodicTask] = []

    def add(self, name: str, target: Callable[[], None], timeout: float):
        """Add a periodic task"""
        self._periodic_tasks.append(
            PeriodicTask(name, target, timeout, event=self._shutdown_event),
        )

    def wait(self, timeout: float):
        """Wait for shutdown_event"""
        self._shutdown_event.wait(timeout)

    def start(self):
        for task in self._periodic_tasks:
            task.start()

    def shutdown(self):
        self._shutdown_event.set()
        for task in self._periodic_tasks:
            task.join(timeout=5.0)
