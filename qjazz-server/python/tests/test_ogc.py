import json

from dataclasses import dataclass
from pathlib import Path

from qgis.core import QgsProject

from qjazz_cache.storage import load_project_from_uri
from qjazz_ogc import Collection, OgcEndpoints
from qjazz_ogc.crs import CrsRef
from qjazz_ogc.stac import CatalogBase
from qjazz_rpc import messages
from qjazz_rpc.tests.worker import Worker

pytest_plugins = ('pytest_asyncio',)


@dataclass
class ProjectLoaderConfig:
    trust_layer_metadata: bool = True
    disable_getprint: bool = True
    force_readonly_layers: bool = True
    dont_resolve_layers: bool = False
    disable_advertised_urls: bool = False
    ignore_bad_layers: bool = True


def load_project(path: Path) -> QgsProject:
    return load_project_from_uri(str(path), ProjectLoaderConfig())


def test_ogc_default_crs(qgis_session: None):

    crs = CrsRef.default()
    print("\n::test_ogc_default_crs::", crs, "->", crs.to_ogc_urn())

    qgis_crs = crs.to_qgis()
    assert qgis_crs.isValid()


def test_ogc_project_collection(qgis_session: None, data: Path):

    project = load_project(data.joinpath('france_parts', 'france_parts.qgs'))

    coll = Collection.from_project("france_parts", project)
    print("\n::test_project_collection::\n", coll.model_dump_json(indent=4))

    assert coll.extent.spatial is not None
    assert coll.extent.temporal.interval == [[None, None]]


async def test_ogc_catalog_api(worker: Worker):
    """ Test worker cache api
    """
    await worker.io.put_message(
        messages.CollectionsMsg(
            start=0,
            end=50,
        ),
    )

    status, resp = await worker.io.read_message()
    print("\n::test_ogc_api::catalog", status)
    assert status == 200

    resp = messages.CollectionsPage.model_validate(resp)

    assert not resp.next
    assert len(resp.items) > 0
    assert len(resp.items) < 50

    schema = json.loads(resp.schema_)
    print("\n::test_ogc_api::catalog::schema\n", schema)

    print("\n::test_ogc_api::catalog::items:")
    print('\n'.join(n.name for n in resp.items))

    item = resp.items[0]
    print("\n::test_ogc_api::catalog::item", item)

    coll = CatalogBase.model_validate_json(item.json_)

    assert coll.id == item.name
    assert item.endpoints == OgcEndpoints.MAP.value


def test_ogc_layer_collection(qgis_session: None, data: Path):

    project = load_project(data.joinpath('france_parts', 'france_parts.qgs'))

    coll = Collection.from_project("france_parts", project)

    for layer in project.layerTreeRoot().customLayerOrder():
        layer_coll = Collection.from_layer(layer, coll)
        print("\n::test_ogc_layer_collection::\n", layer_coll.model_dump_json(indent=4))

        assert layer_coll.id == layer.name()

    assert coll.extent.spatial is not None
    assert coll.extent.temporal.interval == [[None, None]]
