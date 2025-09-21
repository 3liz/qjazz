
from dataclasses import dataclass
from pathlib import Path

from qgis.core import QgsProject

from qjazz_cache.storage import load_project_from_uri
from qjazz_ogc import Collection
from qjazz_ogc.crs import CrsRef


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


def test_ogc_default_crs():
    crs = CrsRef.default()
    print("\n::test_ogc_default_crs::", crs, "->", crs.to_ogc_urn())

    qgis_crs = crs.to_qgis()
    assert qgis_crs.isValid()


def test_ogc_project_collection(data: Path):
    project = load_project(data.joinpath("france_parts", "france_parts.qgs"))

    coll = Collection.from_project("france_parts", project)
    print("\n::test_project_collection::\n", coll.model_dump_json(indent=4))

    assert coll.extent.spatial is not None
    assert coll.extent.temporal is not None
    assert coll.extent.temporal.interval == [[None, None]]


def test_ogc_layer_collection(data: Path):
    project = load_project(data.joinpath("france_parts", "france_parts.qgs"))

    coll = Collection.from_project("france_parts", project)

    for layer in project.layerTreeRoot().customLayerOrder():
        layer_coll = Collection.from_layer(layer, coll)
        print("\n::test_ogc_layer_collection::\n", layer_coll.model_dump_json(indent=4))

        assert layer_coll.id == layer.name()

    assert coll.extent.spatial is not None
    assert coll.extent.temporal is not None
    assert coll.extent.temporal.interval == [[None, None]]
