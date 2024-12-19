#
# Cache management operations
#
from datetime import datetime
from typing import (
    Iterator,
    Optional,
    Tuple,
    assert_never,
    cast,
)
from urllib.parse import urlunsplit

from qgis.core import QgsMapLayer

from qjazz_cache.extras import evict_by_popularity
from qjazz_cache.prelude import (
    CacheEntry,
    CacheManager,
    CheckoutStatus,
    ProjectMetadata,
)
from qjazz_contrib.core import logger
from qjazz_contrib.core.utils import to_iso8601

from . import messages as _m
from .config import QgisConfig

Co = CheckoutStatus

#
# Drop a project from the cache
#


def drop_project(conn: _m.Connection, cm: CacheManager, uri: str, cache_id: str = ""):
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True),
    )

    match status:
        case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
            e = cast(CacheEntry, md)
            _, status = cm.update(e.md, Co.REMOVED)

            reply = _m.CacheInfo(
                uri=e.md.uri,
                in_cache=False,
                last_modified=timestamp_to_iso(e.md.last_modified),
                saved_version=e.project.lastSaveVersion().text(),
                status=status.value,
                cache_id=cache_id,
            )
        case _:
            reply = _m.CacheInfo(
                uri=uri,
                in_cache=False,
                status=status.value,
                cache_id=cache_id,
            )

    _m.send_reply(conn, reply)

# Convert last modified date to ison
def timestamp_to_iso(timestamp: Optional[float]) -> Optional[str]:
    return to_iso8601(
        datetime.fromtimestamp(timestamp),
    ) if timestamp else None

#
# Helper for returning CacheInfo from
# cache entry
#
def cache_info_from_entry(
    e: CacheEntry,
    status: CheckoutStatus,
    in_cache: bool = True,
    cache_id: str = "",
) -> _m.CacheInfo:

    return _m.CacheInfo(
        uri=e.uri,
        in_cache=in_cache,
        timestamp=int(e.timestamp),
        status=status.value,
        name=e.name,
        storage=e.storage,
        last_modified=timestamp_to_iso(e.last_modified),
        saved_version=e.project.lastSaveVersion().text(),
        debug_metadata=e.debug_meta.__dict__.copy(),
        cache_id=cache_id,
        last_hit=int(e.last_hit),
        hits=e.hits,
        pinned=e.pinned,
    )


#
# Checkout project
# and apply update if requested
#
def checkout_project(
    conn: _m.Connection,
    cm: CacheManager,
    config: QgisConfig,
    uri: str,
    pull: bool,
    cache_id: str = "",
):
    try:
        url = cm.resolve_path(uri, allow_direct=True)
        md, status = cm.checkout(url)

        if not pull:
            match status:
                case Co.NEW:
                    md = cast(ProjectMetadata, md)
                    reply = _m.CacheInfo(
                        uri=md.uri,
                        in_cache=False,
                        status=status.value,
                        storage=md.storage or None,
                        last_modified=timestamp_to_iso(md.last_modified),
                        cache_id=cache_id,
                    )
                case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED | Co.UPDATED:
                    reply = cache_info_from_entry(cast(CacheEntry, md), status, cache_id=cache_id)
                case Co.NOTFOUND:
                    reply = _m.CacheInfo(
                        uri=urlunsplit(url),
                        in_cache=False,
                        status=status.value,
                        cache_id=cache_id,
                    )
                case _ as unreachable:
                    assert_never(unreachable)
        else:
            match status:
                case Co.NEW:
                    md = cast(ProjectMetadata, md)
                    if config.max_projects <= len(cm) and not evict_project_from_cache(cm):
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            md.uri,
                        )
                        _m.send_reply(conn, "Max object reached on server", 403)
                        return
                    e, status = cm.update(md, status)
                    e = cast(CacheEntry, e)
                    # Pin the entry since this object has been asked explicitely
                    # in cache
                    e.pin()
                    reply = cache_info_from_entry(e, status, cache_id=cache_id)
                # UPDATED for the sake of exhaustiveness
                case Co.UNCHANGED | Co.UPDATED:
                    e = cast(CacheEntry, e)
                    e.pin()  # See above
                    reply = cache_info_from_entry(e, status, cache_id=cache_id)
                case Co.NEEDUPDATE:
                    e, status = cm.update(cast(CacheEntry, md).md, status)
                    e = cast(CacheEntry, e)
                    e.pin()  # See above
                    reply = cache_info_from_entry(e, status, cache_id=cache_id)
                case Co.REMOVED:
                    e, status = cm.update(cast(CacheEntry, md).md, status)
                    reply = cache_info_from_entry(e, status, False, cache_id=cache_id)
                case Co.NOTFOUND:
                    reply = _m.CacheInfo(
                        uri=urlunsplit(url),
                        in_cache=False,
                        status=status.value,
                        cache_id=cache_id,
                    )
                case _ as unreachable:
                    assert_never(unreachable)

        _m.send_reply(conn, reply)

    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)
    except CacheManager.StrictCheckingFailure as err:
        _m.send_reply(conn, str(err), 422)


#
# Send cache list
#
def send_cache_list(
    conn: _m.Connection,
    cm: CacheManager,
    status_filter: Optional[CheckoutStatus],
    cache_id: str = "",
):
    co = cm.checkout_iter()
    if status_filter:
        co = filter(lambda n: n[1] == status_filter, co)

    def collect() -> Iterator[Tuple[CacheEntry, CheckoutStatus]]:
        for item in co:
            if conn.cancelled:
                break
            yield item

    # Stream CacheInfo
    _m.stream_data(
        conn,
        (
            cache_info_from_entry(
                entry,
                status,
                cache_id=cache_id,
            ) for entry, status in collect()
        ),
    )


#
# Update cache
#
def update_cache(
    conn: _m.Connection,
    cm: CacheManager,
    cache_id: str = "",
):
    def collect() -> Iterator[Tuple[CacheEntry, CheckoutStatus]]:
        for item in cm.update_cache():
            if conn.cancelled:
                break
            yield item

    # Stream CacheInfo
    _m.stream_data(
        conn,
        (
            cache_info_from_entry(
                entry,
                status,
                cache_id=cache_id,
            ) for entry, status in collect()
        ),
    )

#
# Send project info
#


def send_project_info(
    conn: _m.Connection,
    cm: CacheManager,
    uri: str,
    cache_id: str = "",
):
    def _layer(layer_id: str, layer: QgsMapLayer) -> _m.LayerInfo:
        return _m.LayerInfo(
            layer_id=layer_id,
            name=layer.name(),
            source=layer.publicSource(),
            crs=layer.crs().authid(),
            is_valid=layer.isValid(),
            is_spatial=layer.isSpatial(),
        )

    try:
        url = cm.resolve_path(uri, allow_direct=True)
        md, status = cm.checkout(url)

        match status:
            case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
                entry = cast(CacheEntry, md)
                layers = [_layer(n, lyr) for (n, lyr) in entry.project.mapLayers().items()]
                _m.send_reply(
                    conn,
                    _m.ProjectInfo(
                        status=status.value,
                        uri=entry.md.uri,
                        filename=entry.project.fileName(),
                        crs=entry.project.crs().authid(),
                        last_modified=entry.md.last_modified,
                        storage=entry.md.storage or "<none>",
                        has_bad_layers=any(not lyr.is_valid for lyr in layers),
                        layers=layers,
                        cache_id=cache_id,
                    ),
                )
            case Co.NOTFOUND | Co.NEW | Co.UPDATED:
                _m.send_reply(conn, urlunsplit(url), 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)


#
# Send catalog
#
def send_catalog(
    conn: _m.Connection,
    cm: CacheManager,
    location: str | None,
):
    def collect() -> Iterator[Tuple[ProjectMetadata, str]]:
        for item in cm.collect_projects(location):
            if conn.cancelled:
                break
            yield item

    # Stream CacheInfo
    _m.stream_data(
        conn,
        (
            _m.CatalogItem(
                uri=md.uri,
                name=md.name,
                storage=md.storage or "<none>",
                last_modified=to_iso8601(datetime.fromtimestamp(md.last_modified)),
                public_uri=public_path,
            ) for md, public_path in collect()
        ),
    )


#
# Cache eviction
#

def evict_project_from_cache(cm: CacheManager) -> bool:
    """ Evict a project from cache based on
        its `popularity`

        Returns `true` if object has been evicted from the
        cache, `false` otherwise.
    """
    evicted = evict_by_popularity(cm)
    if evicted:
        logger.debug("Evicted '%s' from cache", evicted.uri)

    return bool(evicted)
