"""
    Test Processing executor
"""
""" Test WPS service
"""


import requests
import json


def test_execute_clipbyextent(host):
    """  Test execute process """

    ident = "processes_test:testcliprasterlayer"
    content = {
        "inputs": {
            "INPUT": "raster_layer",
            "EXTENT": {
                "bbox": [ -112, 20, -87, 45 ],
                "crs": "WGS84",
            },
            "OUTPUT": "clipped_layer",
        },
        "outputs": {
            "OUTPUT": {
                "format": {
                    "mediaType": "application/x-ogc-wms+xml; version=1.3.0",
                },
            },
        }
    }

    rv = requests.post(
        f"{host}/processes/{ident}/execution?map=samples/raster_layer",
        json=content,
    )
    print(rv.text)
    assert rv.status_code == 200

    resp = rv.json()
    assert resp['OUTPUT']['type'] == "application/x-ogc-wms+xml; version=1.3.0"

    href = resp['OUTPUT']['href']
    print("\n::test_execute_clipbyextent::OUTPUT::href", href)

    job_id = rv.headers['X-Job-Id']

    # Get the HEAD
    rv = requests.head(f"{host}/jobs/{job_id}/files/OUTPUT.tif")
    assert rv.status_code == 200
    print("\n::test_execute_clipbyextent::HEAD::headers", rv.headers)

    assert rv.headers['Content-Type'] == "image/tiff"
    
