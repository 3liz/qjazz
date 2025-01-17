from time import time


class Instant:

    def __init__(self):
        self.restart()

    def restart(self):
        self._start = time()

    @property
    def elapsed(self) -> float:
        return time() - self._start

    @property
    def elapsed_ms(self) -> int:
        return int(self.elapsed * 1000.0)
