"""
    Test server disponibility
"""
import requests

def test_landing_page(host):
    """ Test landing page
    """
    rv = requests.get(host + "/")
    assert rv.status_code == 200

    data = rv.json()
    assert "links" in data
    rels = set(link["rel"] for link in  data["links"])
    assert "http://www.opengis.net/def/rel/ogc/1.0/conformance" in rels
    assert "http://www.opengis.net/def/rel/ogc/1.0/job-list" in rels


def test_api_specs(host):
    """ Test response from api path
        
        Shourd be open api specs
    """
    rv = requests.get(host + "/api")
    assert rv.status_code == 200

    data = rv.json()
    assert "paths" in data
    assert "definitions" in data
    assert "info" in data

    assert data["openapi"] == "3.0.0"
    assert data["info"]["title"] == "Qjazz-Processes"
