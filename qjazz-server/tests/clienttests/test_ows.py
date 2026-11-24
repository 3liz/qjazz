"""
    Test misc OWS requests
"""
import requests


def test_wms_getlegendgraphic(backend: str) -> None:
    rv = requests.get(
        f"{backend}/",
        params={
            'MAP': '/france/france_parts.qgs',
            'SERVICE': 'WMS',
            'REQUEST': 'GetLegendGraphic',
            'VERSION': '1.3.0',
            'FORMAT': 'image/png',
            'LAYER': 'france_parts',
        },
    )
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'image/png'
    assert rv.content.startswith(b'\x89PNG\r\n\x1a\n')


def test_wfs_getfeature_geojson(backend: str) -> None:
    rv = requests.get(
        f"{backend}/",
        params={
            'MAP': '/france/france_parts.qgs',
            'SERVICE': 'WFS',
            'REQUEST': 'GetFeature',
            'VERSION': '1.1.0',
            'TYPENAME': 'france_parts',
            'OUTPUTFORMAT': 'GeoJSON',
            'MAXFEATURES': '2',
        },
    )
    assert rv.status_code == 200
    assert rv.headers['Content-Type'].startswith('application/vnd.geo+json')

    data = rv.json()
    assert data['type'] == 'FeatureCollection'
    assert len(data['features']) == 2


def test_wms_unsupported_request(backend: str) -> None:
    """Test that an unsupported request returns an OWS exception"""
    rv = requests.get(
        f"{backend}/",
        params={
            'MAP': '/france/france_parts.qgs',
            'SERVICE': 'WMS',
            'REQUEST': 'NoSuchRequest',
        },
    )
    print("\ntest_wms_unsupported_request::", rv.status_code, rv.text)
    assert rv.status_code == 501
    assert b'<ServiceExceptionReport' in rv.content
    assert b'OperationNotSupported' in rv.content
