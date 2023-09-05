import multiprocessing as mp

from .worker import qgis_server_run, setup_server
from .config import WorkerConfig
from .messages import Pipe as _Pipe


class Worker(mp.Process):

    def __init__(self, config: WorkerConfig):
        super().__init__(name=config.name, daemon=True)
        self._worker_conf = config
        self._worker_io, self._child_conn = _Pipe.new()

    def run(self):
        server = setup_server(self._worker_conf)
        qgis_server_run(server, self._child_conn, self._worker_conf)

    @property
    def io(self) -> _Pipe:
        return self._worker_io
