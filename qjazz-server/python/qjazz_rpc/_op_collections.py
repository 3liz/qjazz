import json

from itertools import islice
from typing import (
    Iterator,
    Optional,
)

from qgis.core import (
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.server import QgsServerProjectUtils

from qjazz_cache.prelude import CacheManager
from qjazz_ogc import Catalog, Collection

from . import messages as _m
from ._op_requests import get_project
from .config import QgisConfig


def handle_catalog(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    collection_schema = Collection.model_json_schema()

    catalog = Catalog.get_service()
    catalog.update(cm, not conf.load_project_on_request)

    if msg.resource:
        item = catalog.get(msg.resource)
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


def layer_endpoints(layer: QgsMapLayer) -> _m.OgcEndpoints:
    match layer:
        case QgsVectorLayer():
            endpoints = _m.OgcEndpoints.FEATURES
            if layer.isSpatial():
                endpoints |= _m.OgcEndpoints.MAP
        case QgsRasterLayer():
            endpoints = _m.OgcEndpoints.MAP | _m.OgcEndpoints.COVERAGE
        case _:
            endpoints = _m.OgcEndpoints.NONE

    return endpoints


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

    parent = catalog.get(msg.location)
    if not parent:
        _m.send_reply(conn, "Resource not found: {msg.location}", 404)
        return

    # We need to fully load the project to get access to
    # metadata
    entry, _ = get_project(conn, cm, conf, parent.public_path, False)
    if not entry:
        return

    project = entry.project

    if msg.resource:
        layer = get_layer(project, msg.resource)
        items = [_m.CollectionsItem(
            name=layer.name(),
            json=Collection.from_layer(layer, parent.coll).model_dump_json(),
            endpoints=layer_endpoints(layer).value,
        )] if layer else []
    else:
        def iter_catalog() -> Iterator[_m.CollectionsItem]:
            for layer in islice(iter_layers(project, cm), msg.start, msg.end):
                yield _m.CollectionsItem(
                    name=layer.name(),
                    json=Collection.from_layer(layer, parent.coll).model_dump_json(),
                    endpoints=layer_endpoints(layer).value,
                )

        items = list(iter_catalog())

    collection_schema = Collection.model_json_schema()

    _m.send_reply(
        conn,
        _m.CollectionsPage(
            schema=json.dumps(collection_schema),
            items=items,
            next=(msg.end - msg.start) >= len(items),
        ),
    )


def handle_collection(
    conn: _m.Connection,
    msg: _m.CollectionsMsg,
    cm: CacheManager,
    conf: QgisConfig,
):
    if msg.location is None:
        handle_catalog(conn, msg, cm, conf)
    else:
        handle_layers(conn, msg, cm, conf)


def iter_layers(
    project: QgsProject,
    cm: CacheManager,
) -> Iterator[QgsMapLayer]:
    """ Return the catalog of layers for this project
    """
    restricted_layers = QgsServerProjectUtils.wmsRestrictedLayers(project)

    # root = project.layerTreeRoot()
    # XXX Show only layers displayable with WMS GetMap.
    # TODO handle legends
    for layer in project.mapLayers(True).values():
        if layer.name() not in restricted_layers:
            yield layer


def get_layer(
    project: QgsProject,
    name: str,
) -> Optional[QgsMapLayer]:
    """ Return the catalog of layers for this project
    """
    restricted_layers = QgsServerProjectUtils.wmsRestrictedLayers(project)

    layer = project.mapLayersByName(name)
    if layer and layer not in restricted_layers:
        return layer[0]

    return None
