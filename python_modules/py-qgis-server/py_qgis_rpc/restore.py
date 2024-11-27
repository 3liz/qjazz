
import asyncio
import os
import pickle  # nosec
import tempfile
import traceback

from pathlib import Path

from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError
from typing_extensions import (
    Annotated,
    Iterator,
    List,
    Literal,
    Protocol,
    TypeVar,
    Union,
    cast,
)

from py_qgis_contrib.core import config, logger
from py_qgis_contrib.core.config import SSLConfig

from .messages import CacheInfo
from .messages import CheckoutStatus as Co

#
# Protocols
#


class Worker(Protocol):
    @property
    def name(self) -> str: ...

    async def checkout_project(self, uri: str, pull: bool = False) -> CacheInfo:
        ...


class WorkerPool(Protocol):
    @property
    def workers(self) -> Iterator[Worker]:
        ...

#
# Config
#


class TmpRestoreConfig(config.ConfigBase):
    restore_type: Literal['tmp'] = 'tmp'


class HttpRestoreConfig(config.ConfigBase):
    restore_type: Literal['http'] = 'http'

    url: AnyHttpUrl = Field(
        title="External cache url",
        description=(
            "Retrieve cache list from external http url, for use with the 'external'\n"
            "storage type.\n"
            "The server will issue a GET method against this url at startup.\n"
            "The method should returns a list of projects path in json."
        ),
    )


class HttpsRestoreConfig(config.ConfigBase):
    restore_type: Literal['https'] = 'https'

    url: AnyHttpUrl = Field(
        title="External cache url",
        description=(
            "Retrieve cache list from external https url, for use with the 'external'\n"
            "storage type.\n"
            "The server will issue a GET method against this url at startup.\n"
            "The method should returns a list of projects path in json."
        ),
    )

    ssl: SSLConfig = SSLConfig()


class NoRestoreConfig(config.ConfigBase):
    restore_type: Literal['none'] = 'none'


_CacheRestoreConfig = Union[
    TmpRestoreConfig,
    HttpRestoreConfig,
    HttpsRestoreConfig,
    NoRestoreConfig,
]


CacheRestoreConfig = Annotated[
    _CacheRestoreConfig,
    Field(
        default=NoRestoreConfig(),
        discriminator='restore_type',
        description=(
            "Restore stored cached projets at startup.\n"
            "Note that only projects loaded explicitely with\n"
            "the admin api or from url are candidate for restoration.\n"
            "i.e projects loaded through requests (using\n"
            "'load_project_on_request' option) will not be\n"
            "restored."
        ),

    ),
]

#
# Implementations
#


def _gettempdir() -> Path:
    return Path(os.getenv("CONF_TMPDIR", tempfile.gettempdir()))


class _RestoreBase:

    def __init__(self):
        self._curr = set()

    async def restore(self, pool: WorkerPool):
        pass

    def clear(self):
        pass

    def update(self, resp: CacheInfo):
        pass

    def _pull(self, pool: WorkerPool):
        try:
            logger.trace("Cache list:  %s", self._curr)

            async def _pull(w):
                for uri in self._curr:
                    resp = await w.checkout_project(uri, pull=True)
                    logger.trace(
                        "RESTORE: Loaded %s in worker %s (status %s)",
                        uri, w.name, resp.status.name,
                    )

            # Pull projects into workers
            asyncio.gather(*(_pull(w) for w in pool.workers), return_exceptions=True)
        except Exception:
            logger.error(
                "Failed to load restore list %s",
                traceback.format_exc(),
            )
            raise

    @property
    def projects(self) -> Iterator[str]:
        """ Return an iterator to current stored
            uris
        """
        yield from self._curr

# Define generic Restore type


Restore = TypeVar('Restore', bound=_RestoreBase)


# ==========================
#  Temp file restoration
# ==========================

class TmpRestore(_RestoreBase):

    def __init__(self):
        super().__init__()
        import socket

        try:
            # Get our ip if the hostname is resolvable
            self._addr = socket.gethostbyname(socket.gethostname())
        except Exception:
            # Fallback to pid
            self._addr = os.getpid()

        self._last = set()
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
            if os.stat(path).st_mode & 0o777 != 0o640:
                logger.error(
                    "SECURITY WARNING: %s: has unexpected file mode, "
                    "cache list will not be restored",
                )
                return
            with path.open('rb') as io:
                self._last = pickle.load(io)    # nosec
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
                    self._path.chmod(0o640)
                    self._last = self._curr.copy()
                except Exception:
                    logger.error(
                        "Failed to save restore list %s",
                        traceback.format_exc(),
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


# ==========================
# Http/Https restoration
# ==========================

class CacheList(BaseModel):
    version: str = "1"
    projects: List[str]


class HttpRestore(_RestoreBase):

    def __init__(self, conf: Union[HttpRestoreConfig | HttpsRestoreConfig]):
        self._conf = conf

    async def restore(self, pool: WorkerPool):
        """ Load restore list and pull projects into
            workers
        """
        import aiohttp

        conf = self._conf

        use_ssl = conf.restore_type == 'https'
        ssl_context = cast(HttpsRestoreConfig, conf).ssl.create_ssl_client_context() if use_ssl else False

        async with aiohttp.ClientSession() as session:
            logger.info("** Loading cache configuration from %s **", conf.url)
            try:
                async with session.get(str(conf.url), ssl=ssl_context) as resp:
                    if resp.status == 200:
                        cached = CacheList.model_validate_json(await resp.text())
                        self._curr = set(cached.projects)
                    else:
                        logger.error(
                            f"Failed to get cache configuration from {conf.url} (error {resp.status})",
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


def create_restore_object(conf: CacheRestoreConfig) -> _RestoreBase:

    match conf:
        case TmpRestoreConfig():
            return TmpRestore()
        case HttpRestoreConfig() | HttpsRestoreConfig():
            return HttpRestore(conf)
        case _:
            return RestoreNoop()
