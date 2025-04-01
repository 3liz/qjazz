"""
    Test server disponibility
"""
import requests


def test_root_request(host):
    """ Test response from root path
        
        Shourd be open api specs
    """
    rv = requests.get(host + "/")
    assert rv.status_code == 200

    data = rv.json()
    assert 'paths' in data
    assert 'definitions' in data
    assert 'info' in data

    assert data['info']['title'] == "Qjazz-Processes"
