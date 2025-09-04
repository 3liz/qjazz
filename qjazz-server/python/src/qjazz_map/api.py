from typing import Sequence

from qjazz_ogc.core.collections import Collection
from qjazz_ogc.stac import Link

from qjazz_contrib.core.models import JsonModel, Option


class LandinPage(JsonModel):
    links: Sequence[Link]


# Catalog description
class CatalogDesc(JsonModel):
    name: str
    title: Option[str]
    description: Option[str]
    available: bool


# Catalogs collection
class Catalogs(JsonModel):
    catalogs: Sequence[CatalogDesc]
    links: Sequence[Link]


# Catalog Endpoint
class CatalogEndpoint(JsonModel):
    links: Sequence[Link]


# Dataset description
class DatasetDesc(Collection):
    pass


# Collection description
class CollectionDesc(Collection):
    pass


# Collections
class Collections(JsonModel):
    collections: Sequence[CollectionDesc]
    links: Sequence[Link]
