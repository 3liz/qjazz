#
# Test the qjazz-processes command line
#
import json

from datetime import datetime, timezone
from types import SimpleNamespace

import click
import pytest

from click.testing import CliRunner, Result

from qgis.core import QgsApplication

from qjazz_processes.__main__ import describe_process, list_jobs
from qjazz_processes.processing.prelude import ProcessAlgorithm
from qjazz_processes.schemas import JobStatus


def _invoke(
    command: click.Command,
    args: list[str],
    executor: SimpleNamespace,
    color: bool = False,
) -> Result:
    # Pass a fake executor in place of the configured one
    return CliRunner().invoke(
        command,
        args,
        obj=SimpleNamespace(setup=lambda: executor),
        color=color,
    )


@pytest.mark.native
def test_cli_describe_processes(plugins):
    """All processes are described and displayed

    Optional: QGIS internal algorithms may use parameter types
    which are not supported, depending on the QGIS version
    (e.g. 'native:relief' or 'native:heatmapkerneldensityestimation'
    with QGIS 4).
    """
    failures = []
    undescribed = []
    for alg in QgsApplication.processingRegistry().algorithms():
        if alg.provider().id() == "qgis":
            # The 'qgis' provider (python processing plugin) is internal to QGIS
            # and not supported: some of its algorithms use custom parameter types
            continue
        try:
            description = ProcessAlgorithm(alg).description()
        except Exception as err:
            undescribed.append(f"{alg.id()}: {err!r}")
            continue

        executor = SimpleNamespace(
            update_services=lambda: None,
            describe=lambda service, ident, project=None, d=description: d,
        )
        result = _invoke(describe_process, ["--service", "test", alg.id()], executor)
        if result.exit_code != 0:
            failures.append(f"{alg.id()}: {result.exception!r}")

    assert undescribed == []
    assert failures == []


def _jobs(count: int, status: str = "successful") -> list[JobStatus]:
    return [
        JobStatus(
            job_id=f"6f1d2b9e-3c1a-4d7e-9a0b-{i:012d}",
            process_id="processes_test:testsimplevalue",
            status=status,
            created=datetime.now(timezone.utc),
        )
        for i in range(count)
    ]


def _jobs_executor(jobs: list[JobStatus]) -> SimpleNamespace:
    return SimpleNamespace(
        update_services=lambda: None,
        jobs=lambda service, realm=None, limit=25, cursor=0, with_details=False: jobs[
            cursor : cursor + limit
        ],
    )


def test_cli_jobs_ls_json_pages():
    """Json output spans pages without prompt"""
    jobs = _jobs(5)
    result = _invoke(list_jobs, ["--json", "--limit", "2"], _jobs_executor(jobs))
    assert result.exit_code == 0, result.output
    assert "Press Enter" not in result.output

    # Output is a sequence of json objects
    decoder = json.JSONDecoder()
    text = result.output.strip()
    job_ids = []
    while text:
        obj, end = decoder.raw_decode(text)
        job_ids.append(obj["jobId"])
        text = text[end:].strip()

    assert job_ids == [job.job_id for job in jobs]


def test_cli_jobs_ls_running_color():
    """Running jobs are displayed in yellow"""
    result = _invoke(
        list_jobs,
        ["--short"],
        _jobs_executor(_jobs(1, status="running")),
        color=True,
    )
    assert result.exit_code == 0, result.output
    # ANSI yellow foreground
    assert "\x1b[33m" in result.output
