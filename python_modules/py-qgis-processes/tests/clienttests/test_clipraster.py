"""
    Test Processing executor
"""
""" Test WPS service
"""


import requests
import json


def test_execute_clipbyextent(host):
    """  Test execute process with KV arguments """

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
                    "mediaType": "application/x-ogc-wms; version=1.3.0",
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
    assert resp['OUTPUT']['type'] == "application/x-ogc-wms; version=1.3.0"
