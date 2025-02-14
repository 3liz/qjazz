import requests

from typing import Optional, Sequence

from qjazz_map.api import (
    LandinPage,
    Catalogs,
    CatalogEndpoint,
)

def test_oapi_core_landing_page(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}",
        headers= {'x-request-id': 'test_oapi_core_landing_page'},
    )
    data = resp.json()
    print("\n::test_oapi_core_catalog::data\n", data)

    assert resp.status_code == 200

    LandinPage.model_validate(data)


def test_oapi_core_catalogs(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/catalogs",
        headers= {'x-request-id': 'test_oapi_core_catalogs'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_core_catalogs::data\n", data)

    assert len(data['catalogs']) > 1

    Catalogs.model_validate(data)


def test_oapi_core_catalog(host):
    """ Retrieve catalog
    """
    resp = requests.get(f"http://{host}/test/catalog",
        headers= {'x-request-id': 'test_oapi_core_catalog'},
    )

    assert resp.status_code == 200

    data = resp.json()
    print("\n::test_oapi_core_catalog::data\n", data)

    CatalogEndpoint.model_validate(data)    
