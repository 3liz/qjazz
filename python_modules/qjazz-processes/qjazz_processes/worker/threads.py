
import traceback

from threading import Event, Thread
from typing import Callable

from qjazz_contrib.core import logger


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
