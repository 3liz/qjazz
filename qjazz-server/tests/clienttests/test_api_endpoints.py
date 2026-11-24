"""
    Test QGIS server api endpoints

    Endpoints are defined in the 'test' backend configuration
"""
import pytest
import requests


@pytest.mark.parametrize("endpoint", ("features", "wfs3"))
def test_api_landing_page(backend: str, endpoint: str) -> None:
    resp = requests.get(f"{backend}/{endpoint}")
    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith('application/json')
    assert 'links' in resp.json()


@pytest.mark.parametrize("endpoint", ("features", "wfs3"))
def test_api_collections(backend: str, endpoint: str) -> None:
    resp = requests.get(
        f"{backend}/{endpoint}/collections",
        params={'MAP': '/france/france_parts.qgs'},
    )
    assert resp.status_code == 200

    data = resp.json()
    print(f"\ntest_api_collections::{endpoint}", [c['id'] for c in data['collections']])
    assert len(data['collections']) > 0
