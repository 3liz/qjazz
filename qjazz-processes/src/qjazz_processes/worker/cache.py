import multiprocessing as mp
import traceback

from abc import abstractmethod
from enum import Enum, auto
from typing import (
    Optional,
    Protocol,
    cast,
)

from qjazz_core import logger

from ..processing.config import ProcessingConfig
from ..schemas import (
    JsonDict,
    JsonValue,
    ProcessDescription,
    ProcessSummary,
    ProcessSummaryList,
)


class MsgType(Enum):
    QUIT = auto()
    UPDATE = auto()
    DESCRIBE = auto()
    READY = auto()


POLL_TIMEOUT = 5.0

# Protocol for processes cache description implementations


class ProcessCacheProtocol(Protocol):
    @property
    def processes(self) -> list[JsonValue]: ...

    def describe(self, ident: str, project: Optional[str]) -> JsonDict | None: ...

    def update(self) -> list[ProcessSummary]: ...

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# NOTE: DEPRECATED
ProcessCacheProto = ProcessCacheProtocol

#
# Processes cache
#
# ProcessCache implement description cache computation as a stand alone
# child process. It allows for using QGIS (or other libs that
# are not fork friendly) used when computing job descriptions.
#


class ProcessCache(mp.Process):
    def __init__(self, config: ProcessingConfig) -> None:
        super().__init__(name="process_cache", daemon=True)
        self._descriptions: dict[str, ProcessDescription] = {}
        self._processes: list[ProcessSummary] = []
        self._known_processes: set[str] = set()
        self._processing_config = config

        self._sender, self._conn = mp.Pipe(duplex=True)

    @property
    def processing_config(self) -> ProcessingConfig:
        return self._processing_config

    @property
    def processes(self) -> list[JsonValue]:
        return ProcessSummaryList.dump_python(self._processes, mode="json", exclude_none=True)

    def describe(self, ident: str, project: Optional[str]) -> JsonDict | None:
        """Return process description"""
        if not self.is_alive():
            return None

        if ident not in self._known_processes:
            logger.error("Unknown process '%s'", ident)
            return None

        key = f"{ident}@{project}"

        description = self._descriptions.get(key)
        if not description:
            logger.info("Getting process description for %s, project=%s", ident, project)

            self._sender.send((MsgType.DESCRIBE, ident, project))
            if self._sender.poll(POLL_TIMEOUT):
                description = cast("ProcessDescription", self._sender.recv())
                self._descriptions[key] = description
            else:
                raise RuntimeError(f"Failed to get process description {ident} ({project})")

        return description.model_dump(mode="json", exclude_none=True)

    def update(self) -> list[ProcessSummary]:
        """Update process summary list"""
        if not self.is_alive():
            return []

        logger.info("Updating processes cache")

        self._sender.send((MsgType.UPDATE,))
        if self._sender.poll(POLL_TIMEOUT):
            self._processes = cast("list[ProcessSummary]", self._sender.recv())
        else:
            raise RuntimeError("Failed to update process descriptions")

        self._descriptions.clear()
        self._known_processes = {p.id_ for p in self._processes}

        return self._processes

    def start(self) -> None:
        super().start()
        # Wait for the process to be ready
        self._sender.send((MsgType.READY,))
        if self._sender.poll(10.0):
            self._sender.recv()
        else:
            raise RuntimeError("Failed to start process cache")

    def stop(self) -> None:
        if not self.is_alive():
            logger.info("Cache process alreay stopped")
            return
        self._sender.send((MsgType.QUIT,))
        self.join(5.0)
        if self.exitcode is None:
            logger.error("Failed to terminate cache process")

    def run(self) -> None:
        logger.info("Starting process cache")

        self.initialize()
        try:
            while True:
                msg_id, *data = self._conn.recv()
                try:
                    match msg_id:
                        case MsgType.QUIT:
                            break
                        case MsgType.UPDATE:
                            self._conn.send(self._update())
                        case MsgType.DESCRIBE:
                            self._conn.send(self._describe(*data))
                        case MsgType.READY:
                            logger.info("Process cache ready")
                            self._conn.send(True)
                except Exception as e:
                    logger.error("%s\nCache error: %s", traceback.format_exc(), e)
        except (KeyboardInterrupt, SystemExit):
            pass
        logger.info("Leaving process cache")

    @abstractmethod
    def initialize(self): ...

    @abstractmethod
    def _describe(self, ident: str, project: Optional[str]) -> ProcessDescription: ...

    @abstractmethod
    def _update(self) -> list[ProcessSummary]: ...
