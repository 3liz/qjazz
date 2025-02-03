from dataclasses import dataclass
from pathlib import Path

from qgis.core import QgsProject

from qjazz_cache.storage import load_project_from_uri
from qjazz_ogc.qgis.project import Collection


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


async def test_project_collection(qgis_session: None, data: Path):

    project = load_project(data.joinpath('france_parts', 'france_parts.qgs'))

    coll = Collection.from_project("france_parts", project)
    print("\n::test_project_collection::\n", coll.model_dump_json(indent=4))

    assert coll.extent.spatial is not None
    assert coll.extent.temporal.interval == [[None, None]]
