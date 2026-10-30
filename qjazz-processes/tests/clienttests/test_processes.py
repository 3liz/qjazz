""" Test Processes service
"""
import os
import pytest

from time import sleep
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests


OGC_EXCEPTION_URI = "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0"


def _execute_process(host: str, *, respond_async: bool, tag: Optional[str] = None):
    """ Execute a process and return its status json
    """
    headers: dict = {}
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
    print("\n::test_executeprocess_sync::files", rv.status_code, rv.text)
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

    assert rv.status_code == 404
    assert rv.json()['type'] == f"{OGC_EXCEPTION_URI}/no-such-process"


def test_describe_unknownprocess(host):
    """ Test unknown process description """
    rv = requests.get(f"{host}/processes/processes_test:idonotexists")
    assert rv.status_code == 404
    data = rv.json()
    assert data['details'] == {"processId": "processes_test:idonotexists"}
    assert data['type'] == f"{OGC_EXCEPTION_URI}/no-such-process"
    assert data['status'] == 404


def test_unknownservice(host):
    """ Test unknown service error """
    params = {"service": "idonotexists"}

    rv = requests.get(f"{host}/processes/", params=params)
    assert rv.status_code == 404
    assert rv.json()['details'] == params
    # No specific OGC exception type for unknown service
    assert rv.json()['type'] == "about:blank"

    rv = requests.get(f"{host}/processes/processes_test:testcopylayer", params=params)
    assert rv.status_code == 404

    rv = requests.post(
        f"{host}/processes/processes_test:testcopylayer/execution",
        params=params,
        json={"inputs": {}},
    )
    assert rv.status_code == 404


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


def test_job_list_tag_links(host, data):
    """ Test that tag filter is kept in job list links
    """
    tag = f"test_tag_links_{os.getpid()}"
    for _ in range(2):
        _execute_process(host, respond_async=True, tag=tag)

    def _links(rv) -> dict:
        assert rv.status_code == 200
        return {link['rel']: urlparse(link['href']) for link in rv.json()['links']}

    rv = requests.get(f"{host}/jobs/", params={"tag": tag, "limit": 1})
    assert len(rv.json()['jobs']) == 1
    links = _links(rv)
    assert "next" in links
    for rel in ("self", "next"):
        assert parse_qs(links[rel].query)['tag'] == [tag], rel

    # Follow 'next' link
    rv = requests.get(links['next'].geturl())
    jobs = rv.json()['jobs']
    assert len(jobs) == 1
    assert jobs[0]['tag'] == tag
    links = _links(rv)
    assert "prev" in links
    for rel in ("self", "prev"):
        assert parse_qs(links[rel].query)['tag'] == [tag], rel

    # No tag filter: no 'tag' parameter in links
    rv = requests.get(f"{host}/jobs/", params={"limit": 1})
    links = _links(rv)
    assert "next" in links
    for rel in ("self", "next"):
        assert "tag" not in parse_qs(links[rel].query), rel


def test_job_list_results_link(host, data):
    """ Test results link of successful jobs in job list
    """
    tag = f"test_results_link_{os.getpid()}"
    status = _execute_process(host, respond_async=False, tag=tag)
    job_id = status['jobId']

    rv = requests.get(f"{host}/jobs/", params={"tag": tag})
    assert rv.status_code == 200
    jobs = [job for job in rv.json()['jobs'] if job['jobId'] == job_id]
    assert len(jobs) == 1
    assert jobs[0]['status'] == "successful"

    hrefs = [
        link['href'] for link in jobs[0]['links']
        if link['rel'] == "http://www.opengis.net/def/rel/ogc/1.0/results"
    ]
    assert len(hrefs) == 1
    assert urlparse(hrefs[0]).path.endswith(f"/jobs/{job_id}/results")

    rv = requests.get(hrefs[0])
    assert rv.status_code == 200


def test_job_status_links(host, data):
    """ Test links of a successful job status
    """
    status = _execute_process(host, respond_async=False)
    job_id = status['jobId']

    rv = requests.get(f"{host}/jobs/{job_id}")
    assert rv.status_code == 200
    assert rv.json()['status'] == "successful"

    paths = {urlparse(link['href']).path: link['href'] for link in rv.json()['links']}
    for suffix in ("", "/results", "/log", "/files/"):
        path = f"/jobs/{job_id}{suffix}"
        assert path in paths, path
        rv = requests.get(paths[path])
        assert rv.status_code == 200, path


def test_job_exceptions(host, data):
    """ Test OGC exceptions for jobs
    """
    unknown_job = "00000000-0000-0000-0000-000000000000"
    for path in ("", "/results", "/log", "/files/"):
        rv = requests.get(f"{host}/jobs/{unknown_job}{path}")
        assert rv.status_code == 404, path
        data = rv.json()
        assert data['type'] == f"{OGC_EXCEPTION_URI}/no-such-job", path
        assert data['status'] == 404, path

    rv = requests.delete(f"{host}/jobs/{unknown_job}")
    assert rv.status_code == 404
    assert rv.json()['type'] == f"{OGC_EXCEPTION_URI}/no-such-job"

    # Results of a running job
    rv = requests.post(
        f"{host}/processes/processes_test:testlongprocess/execution",
        json={"inputs": {"DELAY": 30}},
        headers={"Prefer": "respond-async"},
    )
    assert rv.status_code == 202
    job_id = rv.json()['jobId']
    try:
        rv = requests.get(f"{host}/jobs/{job_id}/results")
        assert rv.status_code == 404
        assert rv.json()['type'] == f"{OGC_EXCEPTION_URI}/result-not-ready"
    finally:
        requests.delete(f"{host}/jobs/{job_id}")


def test_invalid_job_id(host, data):
    """ Test that glob patterns are rejected as job id
    """
    status = _execute_process(host, respond_async=True, tag="test_invalid_job_id")

    job_id = status['jobId']

    # Invalid job ids do not match any route: note that the
    # catch-all CORS 'OPTIONS' route turns 404 into 405
    for bad_id in ("*", "%2A", "%3F*", "%5Ba-z%5D*"):
        rv = requests.get(f"{host}/jobs/{bad_id}")
        assert rv.status_code in (404, 405), bad_id
        rv = requests.get(f"{host}/jobs/{bad_id}/log")
        assert rv.status_code in (404, 405), bad_id
        rv = requests.delete(f"{host}/jobs/{bad_id}")
        assert rv.status_code in (404, 405), bad_id

    # The job must still be there
    rv = requests.get(f"{host}/jobs/{job_id}")
    assert rv.status_code == 200
    assert rv.json()['status'] != "dismissed"


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





def test_output_html(host):
    """ Test html output
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testoutputhtml/execution",
        json={"inputs": {}},
    )
    print("\n::test_output_html::", rv.text)
    assert rv.status_code == 200

    link = rv.json()['OUTPUT']
    assert link['type'] == "text/html"
    assert link['description'] == "HTML report"
    assert link['href'].endswith("/report.html")

    # Download the html file
    rv = requests.get(link['href'])
    assert rv.status_code == 200
    assert "hello html" in rv.text
    assert len(rv.content) == link['length']


def test_optional_parameter_omitted(host):
    """ Test omitted optional parameter
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testoptionvalue/execution",
        json={"inputs": {}},
    )
    print("\n::test_optional_parameter_omitted::", rv.text)
    assert rv.status_code == 200
    # QGIS default value is used
    assert rv.json()['OUTPUT'] == "selection is 1"


def test_falsy_parameter_values(host):
    """ Test falsy values for required parameters
    """
    rv = requests.post(
        f"{host}/processes/processes_test:testsimplevalue/execution",
        json={"inputs": {"PARAM1": 0, "PARAM2": "x"}},
    )
    print("\n::test_falsy_parameter_values::", rv.text)
    assert rv.status_code == 200
    assert rv.json()['OUTPUT'] == "0 x"
