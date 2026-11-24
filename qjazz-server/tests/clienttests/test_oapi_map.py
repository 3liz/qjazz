import pytest
import requests

from qjazz_map.models import (
    CollectionDesc,
    Collections,
    DatasetDesc,
)
from qjazz_ogc.core.crs import CRS84

LAYER = "SousQuartiers"


def test_oapi_map_dataset(montpellier: str) -> None:
    """ Retrieve dataset description
    """
    resp = requests.get(montpellier,
        headers= {'x-request-id': 'test_oapi_map_dataset'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_map_dataset::data\n", data)

    model = DatasetDesc.model_validate(data)

    assert model.extent.spatial.crs == CRS84
    assert model.extent.spatial.bbox is not None


def test_oapi_map_dataset_not_found(backend: str) -> None:
    resp = requests.get(f"{backend}/catalog/%2Fnope%2Fnope")
    assert resp.status_code == 404


def test_oapi_map_dataset_conformance(montpellier: str) -> None:
    resp = requests.get(f"{montpellier}/conformance")
    assert resp.status_code == 200

    conforms_to = resp.json()['conformsTo']
    assert "https://www.opengis.net/spec/ogcapi-maps-1/1.0/conf/core" in conforms_to


@pytest.mark.parametrize("mime", ("image/png", "image/webp", "image/jpeg"))
def test_oapi_map_dataset_image(montpellier: str, mime: str) -> None:
    """ Retrieve dataset map image
    """
    resp = requests.get(f"{montpellier}/map",
        headers= {
            'x-request-id': f'test_oapi_map_image_{mime}',
            'accept': f"{mime}, */*",
        },
    )

    assert resp.status_code == 200

    headers = resp.headers
    print("\n::test_oapi_map_dataset_image::headers\n", headers)

    assert resp.headers.get('content-type') == mime
    assert resp.headers.get('content-bbox') is not None
    assert resp.headers.get('content-crs') is not None


def test_oapi_map_dataset_collections(montpellier: str) -> None:
    """ Retrieve dataset collections
    """
    resp = requests.get(f"{montpellier}/maps",
        headers= {'x-request-id': 'test_oapi_map_dataset_collections'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_map_dataset::collections\n", data)

    model = Collections.model_validate(data)
    assert len(model.collections) > 0
    assert any(coll.id == LAYER for coll in model.collections)


def test_oapi_map_collection(montpellier: str) -> None:
    """ Retrieve collection description
    """
    resp = requests.get(f"{montpellier}/maps/{LAYER}")
    assert resp.status_code == 200

    model = CollectionDesc.model_validate(resp.json())
    assert model.id == LAYER

    rels = {link.rel for link in model.links}
    print("\n::test_oapi_map_collection::rels", rels)
    assert "[ogc-rel:map]" in rels
    assert "[ogc-rel:legend]" in rels


def test_oapi_map_collection_not_found(montpellier: str) -> None:
    resp = requests.get(f"{montpellier}/maps/NoSuchLayer")
    assert resp.status_code == 404


def test_oapi_map_collection_image(montpellier: str) -> None:
    """ Retrieve collection map image
    """
    resp = requests.get(f"{montpellier}/maps/{LAYER}/map",
        headers= {'accept': "image/png"},
    )
    assert resp.status_code == 200
    assert resp.headers.get('content-type') == "image/png"
    assert resp.headers.get('content-bbox') is not None
    assert resp.headers.get('content-crs') is not None
    assert resp.content.startswith(b'\x89PNG\r\n\x1a\n')


def test_oapi_map_collection_legend(montpellier: str) -> None:
    """ Retrieve collection legend
    """
    resp = requests.get(f"{montpellier}/maps/{LAYER}/legend")
    assert resp.status_code == 200
    assert resp.headers.get('content-type') == "image/png"
    assert resp.content.startswith(b'\x89PNG\r\n\x1a\n')
