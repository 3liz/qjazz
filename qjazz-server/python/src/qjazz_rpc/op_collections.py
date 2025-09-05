import json

from itertools import islice
from typing import Iterator

from pydantic import TypeAdapter
from qjazz_core import logger
from qjazz_core.timer import Instant
from qjazz_ogc import Catalog, CatalogItem, Collection, LayerAccessor, OgcEndpoints
from qjazz_ogc.stac import CatalogBase

from qgis.core import QgsMapLayer

from qjazz_cache.prelude import CacheManager

from . import messages as _m
from .config import QgisConfig
from .op_requests import get_project

CatatalogA = TypeAdapter(CatalogBase)

#
# Return project's catalog
#


def handle_catalog(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    collection_schema = Collection.model_json_schema()

    catalog = Catalog.get_service()

    if msg.resource:
        # Return single project
        item = catalog.get_and_update(cm, msg.resource)
        items = (
            [
                _m.CollectionsItem(
                    name=item.public_path,
                    json=item.coll.model_dump_json(),
                    endpoints=OgcEndpoints.MAP.value,
                )
            ]
            if item
            else []
        )
    else:
        # Return the full catalog
        instant = Instant()
        catalog.update(cm, not conf.load_project_on_request, prefix=msg.location)
        logger.info("Updated catalog (prefix: '%s') in %s ms", msg.location, instant.elapsed_ms)

        def iter_catalog() -> Iterator[_m.CollectionsItem]:
            for item in islice(catalog.iter(msg.location), msg.start, msg.end):
                yield _m.CollectionsItem(
                    name=item.public_path,
                    json=CatatalogA.dump_json(item.coll),
                    endpoints=OgcEndpoints.MAP.value,
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


def handle_layers(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    if not msg.location:
        _m.send_reply(conn, "Missing location", 500)
        return

    pinned = not conf.load_project_on_request

    catalog = Catalog.get_service()
    catalog.update(cm, pinned)

    parent = catalog.get_and_update(cm, msg.location)
    if not parent:
        _m.send_reply(conn, f"Resource not found: {msg.location}", 404)
        return

    # We need to fully load the project to get access to
    # metadata
    entry, _ = get_project(conn, cm, conf, parent.public_path, False)
    if not entry:
        logger.warning("Collection: to entry found for project <%s>", parent.public_path)
        return

    project = entry.project

    accessor = LayerAccessor(project)

    if msg.resource:
        # We are looking for single layer
        if msg.resource in parent.layers:
            layer = accessor.layer_by_name(msg.resource)
            items = (
                [
                    _m.CollectionsItem(
                        name=msg.resource,
                        json=Collection.from_layer(layer, parent.coll).model_dump_json(),
                        endpoints=parent.layers[msg.resource].value,
                    )
                ]
                if layer
                else []
            )
        else:
            items = []
    else:
        # Return the layers collection set
        def iter_catalog() -> Iterator[_m.CollectionsItem]:
            for layer in islice(iter_layers(accessor, parent), msg.start, msg.end):
                name = accessor.layer_name(layer)
                yield _m.CollectionsItem(
                    name=name,
                    json=Collection.from_layer(layer, parent.coll).model_dump_json(),
                    endpoints=parent.layers[name].value,
                )

        items = list(iter_catalog())

    collection_schema = Collection.model_json_schema()

    _m.send_reply(
        conn,
        _m.CollectionsPage(
            schema=json.dumps(collection_schema),
            items=items,
            next=msg.end < len(parent.layers),
        ),
    )


def handle_collection(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    # Allow searching from prefix
    if msg.location is None or msg.location.endswith("/"):
        handle_catalog(conn, msg, cm, conf)
    else:
        handle_layers(conn, msg, cm, conf)


def iter_layers(accessor: LayerAccessor, item: CatalogItem) -> Iterator[QgsMapLayer]:
    """Return the catalog of layers for this project"""
    # root = project.layerTreeRoot()
    # XXX Show only layers displayable with WMS GetMap.
    for layer in accessor.project.mapLayers(True).values():
        if accessor.layer_name(layer) in item.layers:
            yield layer
