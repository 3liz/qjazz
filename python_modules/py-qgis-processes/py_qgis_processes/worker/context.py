#
# Processing worker
#
import os

from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from string import Template

from typing_extensions import Optional

from qgis.core import QgsProject
from qgis.server import QgsServer

from py_qgis_cache import CacheManager
from py_qgis_cache.extras import evict_by_popularity
from py_qgis_contrib.core import logger
from py_qgis_contrib.core.condition import assert_precondition
from py_qgis_contrib.core.qgis import (
    init_qgis_application,
    init_qgis_server,
    qgis_initialized,
    show_qgis_settings,
)

from ..processing.config import ProcessingConfig


def store_reference_url(
    store_url: Template,
    job_id: str,
    resource: str,
    public_url: Optional[str],
) -> str:
    """ Return a proper reference url for the resource
    """
    return store_url.substitute(
        resource=resource,
        jobId=job_id,
        public_url=public_url or "",
    )


class QgisContext:
    """Qgis context initializer
    """

    PUBLISHED_FILES = ".files"
    EXPIRE_FILE = ".job-expire"

    @classmethod
    def setup(cls, conf: ProcessingConfig):
        """ Initialize qgis """

        debug = logger.isEnabledFor(logger.LogLevel.DEBUG)
        if debug:
            os.environ['QGIS_DEBUG'] = '1'

        #
        # Initialize Qgis application
        #
        init_qgis_application(settings=conf.settings())
        if debug:
            logger.debug(show_qgis_settings())

        #
        # Initialize cache manager
        #
        logger.info("Initializing cache manager...")
        CacheManager.initialize_handlers()
        cm = CacheManager(conf.projects)
        cm.register_as_service()

    def __init__(self, conf: ProcessingConfig):
        assert_precondition(qgis_initialized(), "Qgis context must be intialized")
        self._conf = conf

    def store_reference_url(self, job_id: str, resource: str, public_url: Optional[str]) -> str:
        return store_reference_url(self._conf.store_url, job_id, resource, public_url)

    @cached_property
    def cache_manager(self) -> CacheManager:
        return CacheManager.get_service()

    def project(self, path: str) -> QgsProject:
        from py_qgis_cache import CheckoutStatus as Co

        cm = self.cache_manager

        # Resolve location
        url = cm.resolve_path(path)
        # Check status
        md, status = cm.checkout(url)
        match status:
            case Co.REMOVED:
                cm.update(md, status)  # type: ignore [arg-type]
                raise FileNotFoundError(f"Project {url} was removed")
            case Co.NOTFOUND:
                raise FileNotFoundError(f"Project {url} does no exists")
            case _:
                if status == Co.NEW and len(cm) >= self._conf.max_cached_projects:
                    # Evict project from cache
                    evicted = evict_by_popularity(cm)
                    if evicted:
                        logger.debug("Evicted project from cache: %s", evicted.uri)
                entry, _ = cm.update(md, status)  # type: ignore [arg-type]
                entry.hit_me()
                project = entry.project
        return project


class QgisServerContext:
    """Qgis server context initializer
    """
    server: QgsServer

    @classmethod
    def setup(cls, conf: ProcessingConfig):

        debug = logger.isEnabledFor(logger.LogLevel.DEBUG)
        # Enable qgis server debug verbosity
        if debug:
            os.environ['QGIS_SERVER_LOG_LEVEL'] = '0'
            os.environ['QGIS_DEBUG'] = '1'

        projects = conf.projects
        if projects.trust_layer_metadata:
            os.environ['QGIS_SERVER_TRUST_LAYER_METADATA'] = 'yes'
        if projects.disable_getprint:
            os.environ['QGIS_SERVER_DISABLE_GETPRINT'] = 'yes'

        # Disable any cache strategy
        os.environ['QGIS_SERVER_PROJECT_CACHE_STRATEGY'] = 'off'

        cls.server = init_qgis_server(settings=conf.qgis_settings)
        if debug:
            logger.debug(show_qgis_settings())

        CacheManager.initialize_handlers()
        cm = CacheManager(conf.projects)
        cm.register_as_service()


#
# Utils
#

@contextmanager
def execute_context(workdir: Path, task_id: str):
    with chdir(workdir), logger.logfile(workdir, 'processing'), memlog(task_id):
        yield


@contextmanager
def chdir(workdir: Path):
    # XXX Python 3.11 use `contextlib.chdir`
    curdir = os.getcwd()
    os.chdir(workdir)
    try:
        yield
    finally:
        os.chdir(curdir)


@contextmanager
def memlog(task_id: str):
    import psutil
    process = psutil.Process(os.getpid())
    rss = process.memory_info().rss
    mb = 1024 * 1024.0
    try:
        yield
    finally:
        _leaked = (process.memory_info().rss - rss) / mb
        logger.info("Task %s leaked %.3f Mb", task_id, _leaked)
