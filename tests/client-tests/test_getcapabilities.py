"""
    Test server disponibility
"""
import requests
import lxml.etree as etree

from urllib.parse import urlparse

ns = { "wms": "http://www.opengis.net/wms" }

xlink = "{http://www.w3.org/1999/xlink}"

def test_wms_getcapabilities_hrefs(host):
    """ Test getcapabilities hrefs
    """
    urlref = urlparse(
        f"http://{host}/test/"
        f"?MAP=/france/france_parts.qgs&SERVICE=WMS&request=GetCapabilities",
    )
    rv = requests.get(urlref.geturl())
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/xml; charset=utf-8'

    urlref = urlparse(f"http://{host}/test")

    xml  = etree.fromstring(rv.content)

    elem = xml.findall(".//wms:OnlineResource", ns)
    assert len(elem) > 0

    href = urlparse(elem[0].get(xlink+'href'))
    assert href.scheme   == urlref.scheme
    assert href.hostname == urlref.hostname
    assert href.path     == urlref.path


def test_lower_case_query_params(host):
    """ Test that we support lower case query param
    """
    urlref = f"http://{host}/test/?map=france/france_parts.qgs&SERVICE=WMS&request=GetCapabilities"
    rv = requests.get(urlref)
    assert rv.status_code == 200   


def test_wfs_getcaps_xml(host):
    urlref = f"http://{host}/test/?map=france/france_parts.qgs&SERVICE=WFS"
    rv = requests.post(
        urlref,
        data=b"""<?xml version="1.0" encoding="UTF-8"?>
            <wfs:GetCapabilities
                service="WFS"
                version="1.0.0"
                xmlns:wfs="http://www.opengis.net/wfs"
                xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                xsi:schemaLocation="http://www.opengis.net/wfs/1.0.0 http://schemas.opengis.net/wfs/1.0.0/wfs.xsd">
            </wfs:GetCapabilities>
        """,
        headers={ 'Content-Type':'text/xml; charset=utf-8' },
    )
    print("\ntest_getcaps_wfs_xml::status::", rv.status_code)
    print("\ntest_getcaps_wfs_xml::\n", rv.text)
    assert rv.status_code == 200   
