
import asyncio
import os
import pickle
import tempfile
import traceback

from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError
from typing_extensions import List, Literal, Optional

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.config import SSLConfig, section

from .messages import CacheInfo
from .messages import CheckoutStatus as Co
from .pool import WorkerPool

CACHE_RESTORE_CONFIG_SECTION = "restore_cache"


@section(CACHE_RESTORE_CONFIG_SECTION)
class CacheRestoreConfig(config.Config):
    (
        "Restore stored cached projets at startup.\n"
        "Note that only projects loaded explicitely with\n"
        "the admin api are from url are candidate for restoration.\n"
        "i.e projects loaded through requests (using\n"
        "'load_project_on_request' option) will not be\n"
        "restored."
    )
    ssl: Optional[SSLConfig] = None
    url: Optional[AnyHttpUrl] = Field(
        default=None,
        title="External cache url",
        description=(
            "Retrieve cache list from external url, for use with the 'external'\n"
            "storage type.\n"
            "The server will issue a GET method against this url at startup.\n"
            "The method should returns a list of projects path in json."
        ),
    )
    restore_type: Literal['http', 'tmp', 'none'] = Field(
        default='tmp',
        description=(
            "Storage type used for storing cache list:\n"
            "  'http': use external http/https url.\n"
            "  'tmp' : use internal tmpfile storage.\n"
            "  'none': do not restore anything."
        )
    )


def _gettempdir() -> Path:
    return Path(os.getenv("PY_QGIS_TMPDIR", tempfile.gettempdir()))


class _RestoreBase:

    async def restore(self, pool: WorkerPool):
        pass

    def clear(self):
        pass

    def update(self, uri: str):
        pass

    def _pull(self, pool: WorkerPool):
        try:
            logger.trace("Cache list:  %s", self._curr)

            async def _pull(w):
                for uri in self._curr:
                    resp = await w.checkout_project(uri, pull=True)
                    logger.trace(
                        "RESTORE: Loaded %s in worker %s (status %s)",
                        uri, w.name, resp.status.name
                    )

            # Pull projects into workers
            asyncio.gather(*(_pull(w) for w in pool.workers), return_exceptions=True)
        except Exception:
            logger.error(
                "Failed to load restore list %s",
                traceback.format_exc()
            )
            raise


class TmpRestore(_RestoreBase):

    def __init__(self):
        import socket

        self._addr = socket.gethostbyname(socket.gethostname())
        self._last = set()
        self._curr = set()
        self._path = _gettempdir() / f'{self._addr}.qgis-server.cached'
        self._save_task = None

    async def restore(self, pool: WorkerPool):
        """ Load restore list and pull projects into
            workers
        """
        # Find cached configuration
        # If the temp directory is a persistent volume
        # then find any cached configuration from ourselve
        # or sibling instances
        # Shared configuration may be useful when containers
        # are destroyed (for update) then recreated.
        path = self._path
        if not path.exists():
            try:
                path = next(path.parent.glob('*.qgis-server.cached'))
            except StopIteration:
                # No persistent cache found
                # Nothing to do
                return
        try:
            logger.info("Restoring cache list from %s", path)
            with path.open('rb') as io:
                self._last = pickle.load(io)
                self._curr = self._last.copy()
        except Exception:
            logger.error(
                "Failed to load cache list: %s",
                traceback.format_exc(),
            )

        self._pull(pool)

    def _commit(self):
        if self._last != self._curr and not self._save_task:
            async def _save():
                await asyncio.sleep(10)
                logger.debug("Updating restore cache list")
                try:
                    with self._path.open('wb') as io:
                        pickle.dump(self._curr, io)
                    self._last = self._curr.copy()
                except Exception:
                    logger.error(
                        "Failed to save restore list %s",
                        traceback.format_exc()
                    )
                finally:
                    self._save_task = None
            self._save_task = asyncio.create_task(_save())

    def clear(self):
        self._curr.clear()
        self._commit()

    def update(self, resp: CacheInfo):
        match resp.status:
            case Co.NEW | Co.UPDATED | Co.UNCHANGED:
                self._curr.add(resp.uri)
            case Co.REMOVED | Co.NOTFOUND:
                self._curr.discard(resp.uri)
        self._commit()


class CacheList(BaseModel):
    version: str = "1"
    projects: List[str]


class UrlRestore(_RestoreBase):

    def __init__(self, conf: CacheRestoreConfig):
        self._curr = set()
        self._conf = conf
        if conf.url is None:
            raise ValueError("Missing url for restore_cache configuration")

    async def restore(self, pool: WorkerPool):
        """ Load restore list and pull projects into
            workers
        """
        import aiohttp
        
        conf = self._conf

        if conf.url.scheme == 'https':
            import ssl
            if conf.ssl:
                ssl_context = ssl.create_default_context(cafile=conf.ssl.ca)
                if self.ssl.cert:
                    ssl_context.load_cert_chain(conf.ssl.cert, conf.ssl.key)
            else:
                ssl_context = ssl.create_default_context()
        else:
            ssl_context = False

        async with aiohttp.ClientSession() as session:
            logger.info("** Loading cache configuration from %s **", conf.url)
            try:
                async with session.get(str(conf.url), ssl=ssl_context) as resp:
                    if resp.status == 200:
                        cached = CacheList.model_validate_json(await resp.text())
                        self._curr = set(cached.projects)
                    else:
                        logger.error(
                            f"Failed to get cache configuration from {conf.url} (error {resp.status})"
                        )
            except ValidationError as err:
                logger.error("Invalid cache configuration: %s", err)
            except aiohttp.ClientConnectorSSLError:
                logger.error(f"Failed to get cache configuration from {conf.url}")
                raise

            self._pull(pool)


#
# Dummy restore if restore cache is disabled
#
class RestoreNoop(_RestoreBase):
    pass


Restore = _RestoreBase


def create_restore_object(conf: Optional[CacheRestoreConfig] = None):
    if not conf:
        from py_qgis_contrib.core.config import confservice
        conf = confservice.conf.restore_cache

    match conf.restore_type:
        case "tmp":
            return TmpRestore()
        case "http":
            return UrlRestore(conf)
        case _:
            return RestoreNoop()
