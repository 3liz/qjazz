""" Test WPS service
"""
import os
import pytest

from time import sleep
from urllib.parse import parse_qs, urlparse

import requests


def _execute_process(host: str, *, respond_async: bool):
    """ Execute a process and return its status json
    """
    headers = {}
    if respond_async:
        headers.update(Prefer="respond-async")

    resp = requests.post(
        (
            f"{host}/processes/processes_test:testcopylayer/execution"
            f"?map=france/france_parts"
        ),
        json={
            "inputs": {
                "INPUT": "france_parts",
                "OUTPUT": "france_parts2",
            }
        },
        headers=headers,
    )

    expected = 201 if respond_async else 200

    assert resp.status_code == expected
    return resp.json()


def test_describeprocess(host):
    """ Test describe process """
    rv = requests.get(f"{host}/processes/processes_test:testcopylayer")
    assert rv.status_code == 200


def test_executeprocess_async(host):
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
        },
        headers={'Prefer':'respond-async'}
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


def test_executetimeout(host, data):
    """  Test execute timeout """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testlongprocess/execution"
            f"?map=france/france_parts"
        ),
        json={ "inputs": { "DELAY": 1 }},
        headers={"Prefer": "wait=3"},
    )

    print(rv.text)
    assert rv.status_code == 504


@pytest.mark.skipif(os.getenv('TEST_MODE') != 'runall', reason="Test too long")
def test_verylongprocess(host, data):
    """  Test execute a very long process (30s) """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testlongprocess/execution"
            f"?map=france/france_parts"
        ),
        json={ "inputs": { "DELAY": 3 }},
        headers={"Prefer": "respond-async"},
    )

    print(rv.text)
    assert rv.status_code == 201


def test_executedelete(host, data):
    """ Test delete process
    """
    # Execute a process
    status= _execute_process(host, respond_async=True)

    job_id = status['jobId']

    # Delete the response
    rv = requests.delete(f"{host}/jobs/{job_id}")
    assert rv.status_code == 200

    sleep(2)
    # Get the status and make sure is dismissed
    rv = requests.get(f"{host}/jobs/{job_id}")
    assert rv.status_code == 200
    assert rv.json()['status'] == "dismissed"


def test_handleprocesserror_sync(host, data):
    """  Test execute error """
    rv = requests.post(
        f"{host}/processes/processes_test:testraiseerror/execution",
        json={ "inputs": { "PARAM1": 1 }},
        headers={ 'Prefer': "wait=3" },
    )
    assert rv.status_code == 500


def test_handleprocesserror_async(host, data):
    """  Test execute error """
    rv = requests.post(
        f"{host}/processes/processes_test:testraiseerror/execution",
        json={ "inputs": { "PARAM1": 1 }},
        headers={ 'Prefer': "respond-async" },
    )
    assert rv.status_code == 201

    job_id = rv.json()['jobId']

    sleep(2)
    # Get the status and make sure is failed
    rv = requests.get(f"{host}/jobs/{job_id}")
    assert rv.status_code == 200
    assert rv.json()['status'] == "failed"


def test_enum_parameters(host):
    """ Test parameter enums
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testmultioptionvalue/execution",
        json={ "inputs": { "INPUT": ["value2"] }},
    )
    print(rv.text)
    assert rv.status_code == 200

    # Get result
    resp = rv.json()
    assert resp['OUTPUT'] == 'selection is 1'

def test_badparameter_sync(host):
    """ Test parameter enums
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testmultioptionvalue/execution",
        json={ "inputs": { "INPUT": "badparam" }},

    )
    print(rv.text)
    assert rv.status_code == 400

def test_badparameter_async(host):
    """ Test parameter enums
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testmultioptionvalue/execution",
        json={ "inputs": { "INPUT": "badparam" }},
        headers={'Prefer': 'respond-async' },

    )
    print(rv.text)
    assert rv.status_code == 201
