""" Test WPS service
"""
import os
import pytest

from time import sleep
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests


def _execute_process(host: str, *, respond_async: bool, tag: Optional[str] = None):
    """ Execute a process and return its status json
    """
    headers = {}
    if respond_async:
        headers.update(Prefer="respond-async")

    tag_param=f"&tag={tag}" if tag else ""

    resp = requests.post(
        (
            f"{host}/processes/processes_test:testcopylayer/execution"
            f"?map=france/france_parts{tag_param}"
        ),
        json={
            "inputs": {
                "INPUT": "france_parts",
                "OUTPUT": "france_parts2",
            }
        },
        headers=headers,
    )

    expected = 202 if respond_async else 200

    assert resp.status_code == expected
    data = resp.json()

    # In sync response, job id is passed in header
    if not respond_async:
        data['jobId'] = resp.headers['X-Job-Id']

    return data


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
            f"&tag=test_executeprocess_async"
        ),
        json={
            "inputs": {
                "INPUT": "france_parts",
                "OUTPUT": "france_parts2",
            }
        },
        headers={'Prefer':'respond-async'}
    )

    assert rv.status_code == 202


def test_executeprocess_with_delay(host):
    """  Test execute process """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testcopylayer/execution"
            f"?map=france/france_parts"
            f"&tag=test_executeprocess_with_delay"
        ),
        json={
            "inputs": {
                "INPUT": "france_parts",
                "OUTPUT": "france_parts2",
            }
        },
        headers={'Prefer':'respond-async, delay=60'}
    )

    assert rv.status_code == 202


def test_executeprocess_sync(host):
    """  Test execute process """

    result = _execute_process(host, respond_async=False, tag="test_executeprocess_sync")

    job_id = result['jobId']

    # Get log
    rv = requests.get(f"{host}/jobs/{job_id}/log")
    print("\n", rv.text)
    assert rv.status_code == 200
    assert len(rv.json()['log']) > 0

    # Get files
    rv = requests.get(f"{host}/jobs/{job_id}/files")
    print("\n", rv.text)
    assert rv.status_code == 200
    assert len(rv.json()['files']) > 0


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


@pytest.mark.skipif(os.getenv('TEST_RUN_MODE') != 'all', reason="Takes time")
def test_multiple_processes(host, data):
    """  Test execute timeout """
    # Run multiple request to test message queuing and concurreny
    print("\n")
    for i in range(10):
        rv = requests.post(
            (
                f"{host}/processes/processes_test:testlongprocess/execution"
                f"?map=france/france_parts"
                f"&tag=test_executetimeout"
            ),
            json={ "inputs": { "DELAY": 1 }},
            headers={'Prefer':'respond-async'}
        )
        print(f"::test_multiple_processes::{i}\n", rv.text)
        assert rv.status_code == 202



@pytest.mark.skipif(os.getenv('TEST_RUN_MODE') != 'all', reason="Takes time")
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
    assert rv.status_code == 202


def test_executedelete(host, data):
    """ Test delete process
    """
    # Execute a process
    status= _execute_process(host, respond_async=True, tag="test_executedelete")

    job_id = status['jobId']

    # Delete the response
    rv = requests.delete(f"{host}/jobs/{job_id}")
    print("\n", rv.text)
    assert rv.status_code == 200

    sleep(2)
    # Get the status and make sure is dismissed
    rv = requests.get(f"{host}/jobs/{job_id}")
    print("\n",rv.text)
    assert rv.status_code == 404


def test_handleprocesserror_sync(host, data):
    """  Test execute error """
    rv = requests.post(
        f"{host}/processes/processes_test:testraiseerror/execution",
        json={ "inputs": { "PARAM1": 1 }},
        headers={ 'Prefer': "wait=5" },
    )
    print("\n::test_handleprocesserror_sync::", rv.text) 
    print("\n::test_handleprocesserror_sync::", rv.headers) 
    assert rv.status_code == 500
    assert rv.headers['Content-Type'].startswith("application/json")
    assert "jobId" in rv.json()['details']


def test_handleprocesserror_async(host, data):
    """  Test execute error """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testraiseerror/execution"
            f"?tag=test_handleprocesserror_async"
        ),
        json={ "inputs": { "PARAM1": 1 }},
        headers={ 'Prefer': "respond-async" },
    )
    print("\n::test_handleprocesserror_async::", rv.text) 
    print("\n::test_handleprocesserror_async::", rv.headers) 
 
    assert rv.status_code == 202

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
        (
            f"{host}/processes/processes_test:testmultioptionvalue/execution"
            f"?tag=test_badparameter_sync"
        ),
        json={ "inputs": { "INPUT": "badparam" }},

    )
    print(rv.text)
    assert rv.status_code == 400

def test_badparameter_async(host):
    """ Test parameter enums
    """
    rv = requests.post(
        (
            f"{host}/processes/processes_test:testmultioptionvalue/execution"
            f"?tag=test_badparameter_async"
        ),
        json={ "inputs": { "INPUT": "badparam" }},
        headers={'Prefer': 'respond-async' },

    )
    print(rv.text)
    assert rv.status_code == 202



