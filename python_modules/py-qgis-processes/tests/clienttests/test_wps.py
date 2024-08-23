""" Test WPS service
"""

from time import sleep
from urllib.parse import parse_qs, urlparse

import requests


def test_describeprocess(host):
    """ Test describe process """
    rv = requests.get(f"{host}/processes/processes_test:testcopylayer")
    assert rv.status_code == 200


def test_executeprocess(host):
    """  Test execute process """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testcopylayer/execution"
            f"?map=france/france_parts"
        ),
        json={
            "inputs": {
                "INPUT": "france_parts",
                "OUTPUT": "france_parts2",
            }
        }
    )
    assert rv.status_code == 201


def test_unknownprocess(host):
    """ Test unknown process error """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:idonotexists/execution"
            f"?map=france/france_parts"
        ),
        json={},
    )

    assert rv.status_code == 403
    resp = Response(rv)


def test_executetimeout(host, data):
    """  Test execute timeout """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testlongprocess/execution"
            f"?map=france/france_parts&timeout=3"
        )
    )
    assert rv.status_code == 504


def test_executedelete(host, data):
    """ Test delete process
    """
    # Execute a process
    uuid = _execute_process(host)

    # Get the status and make sure is 200
    rv = requests.get(host + f"/status/{uuid}?SERVICE=WPS")
    assert rv.status_code == 200
    assert rv.json()['status'].get('uuid') == uuid

    # Delete the response
    rv = requests.delete(host + f"/status/{uuid}?SERVICE=WPS")
    assert rv.status_code == 200

    # Get the status and make sure is 404
    rv = requests.get(host + f"/status/{uuid}?SERVICE=WPS")
    assert rv.status_code == 404


def test_proxy_status_url(host):
    """ Test that status url has correct host
    """
    # Execute a process
    uuid = _execute_process(host)

    proxy_loc = 'http://test.proxy.loc:8080/'

    # Get the status and make sure is 200
    rv = requests.get(host + f"/status/{uuid}?SERVICE=WPS",
            headers={'X-Forwarded-Url': proxy_loc})
    assert rv.status_code == 200

    st = rv.json()['status']

    # Parse the host url
    status_url = urlparse(st['status_url'])
    assert "{0.scheme}://{0.netloc}/".format(status_url) == proxy_loc


def test_handleprocesserror_sync(host, data):
    """  Test execute error """
    rv = requests.get(
        host + (
            "/ows/?SERVICE=WPS"
            "&Request=Execute"
            "&Identifier=pyqgiswps_test:testraiseerror"
            "&Version=1.0.0"
            "&MAP=france_parts&DATAINPUTS=PARAM1=1&TIMEOUT=3"
        ),
    )
    assert rv.status_code == 500


def test_handleprocesserror_async(host, data):
    """  Test execute error """
    rv = requests.get(
        host + (
            "/ows/?SERVICE=WPS"
            "&Request=Execute"
            "&Identifier=pyqgiswps_test:testraiseerror"
            "&Version=1.0.0"
            "&MAP=france_parts&DATAINPUTS=PARAM1=1&TIMEOUT=3"
            "&StoreExecuteResponse=true"
        ),
    )
    resp = Response(rv)
    assert resp.status_code == 200

    # Get the status url
    status_url = resp.xpath_attr('/wps:ExecuteResponse', 'statusLocation')
    # Get the uuid
    q = parse_qs(urlparse(status_url).query)
    assert 'uuid' in q
    uuid = q['uuid'][0]

    sleep(3)

    # Get the status and make sure is 200
    rv = requests.get(host + f"/status/{uuid}")
    assert rv.status_code == 200

    data = rv.json()
    assert data['status']['status'] == 'ERROR_STATUS'


def test_enum_parameters(host):
    """ Test parameter enums
    """
    rv = requests.get(
        host + (
            "/ows/?SERVICE=WPS"
            "&Request=Execute"
            "&Identifier=pyqgiswps_test:testmultioptionvalue"
            "&Version=1.0.0"
            "&MAP=france_parts&DATAINPUTS=INPUT=value2"
        ),
    )
    assert rv.status_code == 200

    # Get result
    resp = Response(rv)
    assert resp.xpath_text(
        '//wps:ProcessOutputs/wps:Output/wps:Data/wps:LiteralData',
    ) == 'selection is 1'


# def test_slowprogress( host, data ):
#    """  Test execute timeout """
#    rv = requests.get(host+("?SERVICE=WPS&Request=Execute&Identifier=pyqgiswps_test:testlongprocess&Version=1.0.0"
#                               "&MAP=france_parts&DATAINPUTS=PARAM1=2"))
#    assert rv.status_code == 200
