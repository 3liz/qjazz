"""
    Test admin api

    Admin api is enabled for the 'test' backend
    with undisclosed project's uris.
"""
import pytest
import requests

PROJECT = "/france/france_parts"

# See qjazz_cache.status.CheckoutStatus
UNCHANGED = 0
NOTFOUND = 3


def test_admin_landing_page(backend: str) -> None:
    rv = requests.get(f"{backend}/admin")
    assert rv.status_code == 200

    data = rv.json()
    hrefs = {link['href'] for link in data['links']}
    print("\ntest_admin_landing_page::hrefs", hrefs)
    assert f"{backend}/admin/plugins" in hrefs
    assert f"{backend}/admin/catalog" in hrefs
    assert f"{backend}/admin/stats" in hrefs


def test_admin_catalog(backend: str) -> None:
    rv = requests.get(f"{backend}/admin/catalog")
    assert rv.status_code == 200

    items = rv.json()['items']
    public_uris = {item['publicUri'] for item in items}
    assert "/france/france_parts.qgs" in public_uris
    assert "/montpellier/montpellier.qgs" in public_uris

    # Uris are undisclosed
    assert all(item['uri'].startswith('undisclosed:') for item in items)


def test_admin_catalog_location(backend: str) -> None:
    rv = requests.get(f"{backend}/admin/catalog/france")
    assert rv.status_code == 200

    items = rv.json()['items']
    assert len(items) > 0
    assert all(item['publicUri'].startswith('/france/') for item in items)


def test_admin_plugins(backend: str) -> None:
    rv = requests.get(f"{backend}/admin/plugins")
    assert rv.status_code == 200

    data = rv.json()
    assert 'items' in data


def test_admin_project_cache(backend: str) -> None:
    """Test pull/get/delete project in cache"""
    # Pull project
    rv = requests.post(f"{backend}/admin/projects", json={'uri': PROJECT})
    assert rv.status_code == 200

    data = rv.json()
    print("\ntest_admin_project_cache::pull", data)
    assert data['inCache'] is True
    assert data['pinned'] is True
    assert data['name'] == 'france_parts'
    assert data['uri'].startswith('undisclosed:')

    # Get project status
    rv = requests.get(f"{backend}/admin/projects{PROJECT}")
    assert rv.status_code == 200
    data = rv.json()
    assert data['inCache'] is True
    assert data['status'] == UNCHANGED

    # Get project status with query parameter
    rv = requests.get(f"{backend}/admin/projects", params={'uri': PROJECT})
    assert rv.status_code == 200
    assert rv.json()['inCache'] is True

    # Get project details
    rv = requests.get(f"{backend}/admin/projects{PROJECT}", params={'details': 'true'})
    assert rv.status_code == 200
    data = rv.json()
    print("\ntest_admin_project_cache::details", data)
    assert data['filename'] == '<undisclosed>'
    assert data['hasBadLayers'] is False
    assert any(layer['name'] == 'france_parts' for layer in data['layers'])

    # List cached projects
    rv = requests.get(f"{backend}/admin/projects")
    assert rv.status_code == 200
    assert any(item['name'] == 'france_parts' for item in rv.json()['items'])

    # Drop project from cache
    rv = requests.delete(f"{backend}/admin/projects{PROJECT}")
    assert rv.status_code == 200

    rv = requests.get(f"{backend}/admin/projects")
    assert rv.status_code == 200
    assert not any(item['name'] == 'france_parts' for item in rv.json()['items'])


def test_admin_project_not_found(backend: str) -> None:
    rv = requests.get(f"{backend}/admin/projects/france/i_do_not_exists")
    assert rv.status_code == 200

    data = rv.json()
    assert data['status'] == NOTFOUND
    assert data['inCache'] is False


def test_admin_pull_invalid_uri(backend: str) -> None:
    rv = requests.post(f"{backend}/admin/projects", json={'uri': ''})
    assert rv.status_code == 400


def test_admin_stats(backend: str) -> None:
    """Test backend stats"""
    rv = requests.get(f"{backend}/admin/stats")
    assert rv.status_code == 200

    data = rv.json()
    print("\ntest_admin_stats::stats", data)

    active = data['activeWorkers']
    idle = data['idleWorkers']
    assert active >= 0
    assert idle >= 0
    assert data['numProcesses'] >= 1

    # Ratios
    for key in ('activity', 'failurePressure', 'requestPressure'):
        assert 0.0 <= data[key] <= 1.0, key
    if active + idle > 0:
        assert data['activity'] == pytest.approx(active / (active + idle))

    assert data['waitingRequests'] >= 0
    assert data['waitTimeMaxUs'] <= data['waitTimeTotalUs']

    # Cumulative counters must not decrease between two samples
    rv = requests.get(f"{backend}/admin/stats")
    assert rv.status_code == 200
    data2 = rv.json()
    for key in ('uptime', 'waitCount', 'waitTimeTotalUs', 'waitTimeMaxUs'):
        assert data2[key] >= data[key], key

