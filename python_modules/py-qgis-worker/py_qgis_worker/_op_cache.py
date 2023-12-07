#
# Cache management operations
#
from multiprocessing.connection import Connection
from time import time
from urllib.parse import urlunsplit

from typing_extensions import Optional, assert_never

from py_qgis_cache import CacheEntry, CacheManager, CheckoutStatus
from py_qgis_contrib.core import logger

from . import messages as _m
from .config import WorkerConfig

Co = CheckoutStatus


#
# Drop a project from the cache
#
def drop_project(conn: Connection, cm: CacheManager, uri: str, cache_id: str = ""):
    md, status = cm.checkout(
        cm.resolve_path(uri, allow_direct=True)
    )

    match status:
        case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
            e, status = cm.update(md, Co.REMOVED)
            reply = _m.CacheInfo(
                uri=md.uri,
                in_cache=False,
                last_modified=md.last_modified,
                saved_version=e.project.lastSaveVersion().text(),
                status=status,
                cache_id=cache_id,
            )
        case _:
            reply = _m.CacheInfo(
                uri=uri,
                in_cache=False,
                status=status,
                cache_id=cache_id,
            )

    _m.send_reply(conn, reply)


#
# Helper for returning CacheInfo from
# cache entry
#
def _cache_info_from_entry(e: CacheEntry, status, in_cache=True, cache_id: str = "") -> _m.CacheInfo:
    return _m.CacheInfo(
        uri=e.uri,
        in_cache=in_cache,
        timestamp=e.timestamp,
        status=status,
        name=e.name,
        storage=e.storage,
        last_modified=e.last_modified,
        saved_version=e.project.lastSaveVersion().text(),
        debug_metadata=e.debug_meta.__dict__.copy(),
        cache_id=cache_id,
        last_hit=e.last_hit,
        hits=e.hits,
        pinned=e.pinned,
    )


#
# Checkout project
# and apply update if requested
#
def checkout_project(
    conn: Connection,
    cm: CacheManager,
    config: WorkerConfig,
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
                    reply = _m.CacheInfo(
                        uri=md.uri,
                        in_cache=False,
                        status=status,
                        storage=md.storage,
                        last_modified=md.last_modified,
                        cache_id=cache_id,
                    )
                case Co.NEEDUPDATE | Co.UNCHANGED | Co.REMOVED:
                    reply = _cache_info_from_entry(md, status, cache_id=cache_id)
                case Co.NOTFOUND:
                    reply = _m.CacheInfo(
                        uri=urlunsplit(url),
                        in_cache=False,
                        status=status,
                        cache_id=cache_id,
                    )
                case _ as unreachable:
                    assert_never(unreachable)
        else:
            match status:
                case Co.NEW:
                    if config.max_projects <= len(cm) and not evict_project_from_cache(cm):
                        logger.error(
                            "Cannot add NEW project '%s': Maximum projects reached",
                            md.uri,
                        )
                        _m.send_reply(conn, "Max object reached on server", 403)
                        return
                    e, status = cm.update(md, status)
                    # Pin the entry since this object has been asked explicitely
                    # in cache
                    e.pin()
                    reply = _cache_info_from_entry(e, status, cache_id=cache_id)
                case Co.UNCHANGED:
                    md.pin()  # See above
                    reply = _cache_info_from_entry(md, status, cache_id=cache_id)
                case Co.NEEDUPDATE:
                    e, status = cm.update(md, status)
                    e.pin()  # See above
                    reply = _cache_info_from_entry(e, status, cache_id=cache_id)
                case Co.REMOVED:
                    e, status = cm.update(md, status)
                    reply = _cache_info_from_entry(e, status, False, cache_id=cache_id)
                case Co.NOTFOUND:
                    reply = _m.CacheInfo(
                        uri=urlunsplit(url),
                        in_cache=False,
                        status=status,
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
    conn: Connection,
    cm: CacheManager,
    status_filter: Optional[CheckoutStatus],
    cache_id: str = "",
):
    co = cm.checkout_iter()
    if status_filter:
        co = filter(lambda n: n[1] == status_filter, co)

    count = len(cm)
    _m.send_reply(conn, count)
    if count:
        # Stream CacheInfo
        for entry, status in co:
            _m.send_reply(
                conn,
                _cache_info_from_entry(entry, status, cache_id=cache_id),
                206,
            )
        # EOT
        _m.send_reply(conn, None)


#
# Update cache
#
def update_cache(
    conn: Connection,
    cm: CacheManager,
    cache_id: str = "",
):
    for entry, status in cm.update_cache():
        # Stream CacheInfo
        _m.send_reply(
            conn,
            _cache_info_from_entry(entry, status, cache_id=cache_id),
            206,
        )
    # EOT
    _m.send_reply(conn, None)

#
# Send project info
#


def send_project_info(
    conn: Connection,
    cm: CacheManager,
    uri: str,
    cache_id: str = "",
):
    def _layer(layer_id: str, layer):
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
                layers = [_layer(n, l) for (n, l) in md.project.mapLayers().items()]
                _m.send_reply(
                    conn,
                    _m.ProjectInfo(
                        status=status,
                        uri=md.uri,
                        filename=md.project.fileName(),
                        crs=md.project.crs().authid(),
                        last_modified=md.last_modified,
                        storage=md.storage,
                        has_bad_layers=any(not lyr.is_valid for lyr in layers),
                        layers=layers,
                        cache_id=cache_id,
                    )
                )
            case Co.NOTFOUND | Co.NEW:
                _m.send_reply(conn, urlunsplit(url), 404)
            case _ as unreachable:
                assert_never(unreachable)
    except CacheManager.ResourceNotAllowed as err:
        _m.send_reply(conn, str(err), 403)


#
# Send catalog
#
def send_catalog(
    conn: Connection,
    cm: CacheManager,
    location: str,
):
    _m.send_reply(conn, None)
    # Stream CacheInfo
    for md, public_path in cm.collect_projects(location):
        _m.send_reply(
            conn,
            _m.CatalogItem(
                uri=md.uri,
                name=md.name,
                storage=md.storage,
                last_modified=md.last_modified,
                public_uri=public_path,
            ),
            206,
        )
    _m.send_reply(conn, None)


#
# Cache eviction
#

def evict_project_from_cache(cm: CacheManager) -> bool:
    """ Evict a project from cache based on
        its `popularity`

        Returns `true` if object has been evicted from the
        cache, `false` otherwise.
    """
    # Evaluate an euristics based on last_hit timestamp
    # and hits number
    # This is simple model of cache frequency eviction.
    # Such model is related to `hyperbolic policy`:
    # https://www.usenix.org/system/files/conference/atc17/atc17-blankstein.pdf
    # Where eviction scheme is based on popularity over a time period.
    #
    # Here we take the number of hits divided by the  lifetime period
    # of the object in cache
    #
    # This should be ok as long the rate of insertion of new object is low
    # which we assume is the case for this kind of resource.
    now = time()

    candidate = min(
        (e for e in cm.iter() if not e.pinned),
        default=None,
        key=lambda e: e.hits / (now - e.timestamp)
    )

    if not candidate:
        return False

    logger.debug("Evicting '%s' from cache", candidate.uri)
    cm.update(candidate,  Co.REMOVED)
    return True
