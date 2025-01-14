
from pathlib import Path
from typing import Callable


class WatchFile:

    def __init__(self, path: Path, target: Callable[[], None]):
        self._path = path
        self._target = target
        self._last_modified_time = 0.
        if self._path.exists():
            self._last_modified_time = self._path.stat().st_mtime

    def __call__(self):
        if not self._path.exists():
            return
        modified_time = self._path.stat().st_mtime
        if modified_time > self._last_modified_time:
            self._last_modified_time = modified_time
            self._target()
