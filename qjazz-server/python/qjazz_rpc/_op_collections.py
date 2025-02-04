import json

from itertools import islice
from typing import (
    Iterator,
    assert_never,
)

from qjazz_cache.prelude import CacheManager
from qjazz_ogc import Catalog

from . import messages as _m
from .config import QgisConfig


def handle_catalog(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    from qjazz_ogc.project import Collection

    collection_schema = Collection.model_json_schema()

    catalog = Catalog.get_service()
    catalog.update(cm, not conf.load_project_on_request)

    if msg.location:
        item = catalog.get(msg.location)
        items = [_m.CollectionsItem(
            name=item.public_path,
            json=item.coll.model_dump_json(),
            endpoints=_m.OgcEndpoints.MAP.value,
        )] if item else []
    else:
        def iter_catalog() -> Iterator[_m.CollectionsItem]:

            for item in islice(catalog.iter(), msg.start, msg.end):

                yield _m.CollectionsItem(
                    name=item.public_path,
                    json=item.coll.model_dump_json(),
                    endpoints=_m.OgcEndpoints.MAP.value,
                )

        items = list(iter_catalog())

    _m.send_reply(
        conn,
        _m.CollectionsPage(
            schema=json.dumps(collection_schema),
            items=items,
            next=msg.end < len(catalog),
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
