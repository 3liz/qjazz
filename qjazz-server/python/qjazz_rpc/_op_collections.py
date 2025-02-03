import json
import traceback

from dataclasses import dataclass
from itertools import islice
from typing import (
    Iterator,
    Optional,
    Tuple,
    assert_never,
)
from urllib.parse import quote

from pydantic import HttpUrl

from qgis.core import QgsProject

from qjazz_cache.prelude import (
    CacheManager,
    CheckoutStatus,
)
from qjazz_cache.storage import load_project_from_uri
from qjazz_contrib.core import logger
from qjazz_ogc import Link

from . import messages as _m
from .config import QgisConfig

Co = CheckoutStatus


@dataclass(frozen=True)
class FastLoaderConfig:
    trust_layer_metadata: bool = True
    disable_getprint: bool = True
    force_readonly_layers: bool = True
    dont_resolve_layers: bool = True
    disable_advertised_urls: bool = False
    ignore_bad_layers: bool = True


def iter_pinned_projects(
    cm: CacheManager,
    location: Optional[str],
    conf: QgisConfig,
) -> Iterator[Tuple[QgsProject, str]]:
    """ List only pinned projects in cache
    """
    public_paths = {md.uri: public_path for md, public_path in cm.collect_projects(location)}

    for entry in cm.iter():
        if not entry.pinned:
            continue

        co_status = cm.checkout_entry(entry)
        match co_status:
            case Co.UNCHANGED | Co.UPDATED:
                pass
            case Co.NEEDUPDATE:
                if conf.reload_outdated_project_on_request:
                    entry, _ = cm.update(entry.md, co_status)
            case _:
                continue

        # XXX: there is no way to easily reverse from uri to public_path
        # Collect projects from location and find the match for uri
        public_path = public_paths.get(entry.uri)
        if public_path:
            yield (entry.project, public_path)


def iter_projects(
    cm: CacheManager,
    location: Optional[str],
    conf: QgisConfig,
    start: int,
    end: int,
) -> Iterator[QgsProject]:

    if conf.load_project_on_request:
        # Iterate over the whole catalog
        # TODO use cache
        loader_config = FastLoaderConfig()
        for md, public_path in islice(cm.collect_projects(location), start, end):
            try:
                project = load_project_from_uri(md.uri, loader_config)
                yield (project, public_path)
            except Exception:
                logger.error(
                    "Error loading project snapshot:%s\n%s",
                    md.uri,
                    traceback.format_exc(),
                )
    else:
        yield from islice(iter_pinned_projects(cm, location, conf), start, end)


def handle_catalog(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    from qjazz_ogc.qgis.project import Collection

    collection_schema = Collection.model_json_schema()

    href_base = msg.base_url.removesuffix('/')

    def iter_catalog() -> Iterator[_m.CollectionsItem]:
        for project, public_path in iter_projects(
            cm,
            msg.location,
            conf,
            msg.start,
            msg.end,
        ):
            ident = quote(public_path, safe='')
            coll = Collection.from_project(ident, project)
            coll.links.append(
                Link(
                    href=HttpUrl(f"{href_base}/{ident}/map"),
                    rel="related",
                    media_type="application/octet-stream",
                    title="Map",
                    description="Return a displayable map of the dataset",
                ),
            )

            yield _m.CollectionsItem(
                id=ident,
                name=public_path,
                json=coll.model_dump_json(),
                endpoints=_m.OgcEndpoints.MAP.value,
            )

    items = list(iter_catalog())

    _m.send_reply(
        conn,
        _m.CollectionsPage(
            schema=json.dumps(collection_schema),
            next=len(items) > (msg.end - msg.start),
            items=items,
        ),
    )


def handle_collection(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    match msg.type:
        case _m.CollectionsType.CATALOG:
            handle_catalog(conn, msg, cm, conf)
        case _m.CollectionsType.DATASET:
            _m.send_reply(conn, "Not implemented", 501)
        case _ as unreachable:
            assert_never(unreachable)
