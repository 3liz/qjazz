"""
    Test server disponibility
"""
import pytest
import requests


def test_ping(host: str) -> None:
    """Test server liveness endpoint"""
    rv = requests.head(f"http://{host}/ping")
    assert rv.status_code == 200


@pytest.mark.parametrize("service", ("WMS", "WFS", "WCS"))
def test_getcaps(host: str, service: str) -> None:
    """Test GetCapabilities for OWS services"""
    rv = requests.get(
        f"http://{host}/test/?MAP=/france/france_parts.qgs&SERVICE={service}&request=GetCapabilities",
    )
    print(f"\ntest_getcaps::{service}::body", rv.content[:500])
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'


def test_map_path_without_leading_slash(host: str) -> None:
    """Test that MAP path without leading '/' is resolved"""
    rv = requests.get(f"http://{host}/test/?MAP=france/france_parts.qgs&SERVICE=WMS&request=GetCapabilities")
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'


def test_map_not_found_return_404(host: str) -> None:
    """ Test that non existent map return 404
    """
    rv = requests.get(f"http://{host}/test/?MAP=/france/i_do_not_exists.qgs&SERVICE=WFS&request=GetCapabilities")
    assert rv.status_code == 404


def test_unknown_route_return_404(host: str) -> None:
    """Test that a route not bound to any backend return 404"""
    rv = requests.get(f"http://{host}/i_am_not_a_backend/catalog")
    assert rv.status_code == 404
