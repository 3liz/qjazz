"""
    Test server disponibility
"""
import requests


def test_wms_getcaps( host ):
    """ Test 
    """
    rv = requests.get(f"http://{host}/test/?MAP=france/france_parts.qgs&SERVICE=WMS&request=GetCapabilities")
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'


def test_wfs_getcaps( host ):
    """ Test 
    """
    rv = requests.get(f"http://{host}/test/?MAP=/france/france_parts.qgs&SERVICE=WFS&request=GetCapabilities")
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'


def test_wcs_getcaps( host ):
    """ Test 
    """
    rv = requests.get(f"http://{host}/test/?MAP=/france/france_parts.qgs&SERVICE=WCS&request=GetCapabilities")
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'

def test_map_not_found_return_404( host ):
    """ Test that non existent map return 404
    """
    rv = requests.get(f"http://{host}/test/?MAP=/france/i_do_not_exists.qgs&SERVICE=WFS&request=GetCapabilities")
    assert rv.status_code == 404


