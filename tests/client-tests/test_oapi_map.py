import requests

from qjazz_ogc.core.crs import CRS84
from qjazz_map.api import (
    DatasetDesc,
    Collections,
)


def test_oapi_map_dataset(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog/%2Fmontpellier%2Fmontpellier",
        headers= {'x-request-id': 'test_oapi_map_dataset'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_map_dataset::data\n", data)

    model = DatasetDesc.model_validate(data) 

    assert model.extent.spatial.crs == CRS84 
    assert model.extent.spatial.bbox is not None


def test_oapi_map_dataset_image_png(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog/%2Fmontpellier%2Fmontpellier/map",
        headers= {
            'x-request-id': 'test_oapi_map_image_png',
            'accept': "image/png, */*",
        },
    )

    assert resp.status_code == 200

    headers = resp.headers
    print("\n::test_oapi_map_dataset::headers\n", headers)

    assert resp.headers.get('content-type') == "image/png"
    assert resp.headers.get('content-bbox') is not None
    assert resp.headers.get('content-crs') is not None


def test_oapi_map_dataset_image_webp(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog/%2Fmontpellier%2Fmontpellier/map",
        headers= {
            'x-request-id': 'test_oapi_map_image_webp',
            'accept': "image/webp, */*",
        },
    )

    assert resp.status_code == 200

    headers = resp.headers
    print("\n::test_oapi_map_dataset::headers\n", headers)

    assert resp.headers.get('content-type') == "image/webp"
    assert resp.headers.get('content-bbox') is not None
    assert resp.headers.get('content-crs') is not None


def test_oapi_map_dataset_image_jpeg(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog/%2Fmontpellier%2Fmontpellier/map",
        headers= {
            'x-request-id': 'test_oapi_map_image_jpeg',
            'accept': "image/jpeg, */*",
        },
    )

    assert resp.status_code == 200

    headers = resp.headers
    print("\n::test_oapi_map_dataset::headers\n", headers)

    assert resp.headers.get('content-type') == "image/jpeg"
    assert resp.headers.get('content-bbox') is not None
    assert resp.headers.get('content-crs') is not None

def test_oapi_map_dataset_collections(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog/%2Fmontpellier%2Fmontpellier/maps",
        headers= {'x-request-id': 'test_oapi_map_dataset_collections'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_map_dataset::collections\n", data)

    model = Collections.model_validate(data)
    assert len(model.collections) > 0
