#
# Test generic job request handling in 'before_start'
#
from types import SimpleNamespace
from typing import Any

import pytest

from qjazz_core.celery import Job

from qjazz_processes.schemas import JobExecute
from qjazz_processes.worker import generic, registry
from qjazz_processes.worker.generic import GenericJob


class _GenericJob(GenericJob):
    # Replace Celery app binding
    app = SimpleNamespace(conf=SimpleNamespace(task_time_limit=3660, result_expires=900))  # type: ignore [assignment]


@pytest.fixture()
def job(monkeypatch: pytest.MonkeyPatch) -> GenericJob:
    # Registered and not dismissed job
    ti = SimpleNamespace(dismissed=0)
    monkeypatch.setattr(generic.registry, "find_job", lambda app, task_id: ti)
    monkeypatch.setattr(generic.registry, "set_expiration", lambda app, task_id, timeout: True)
    assert generic.registry is registry
    return object.__new__(_GenericJob)


def _task_kwargs(request: JobExecute) -> dict[str, Any]:
    # Task arguments as sent by the executor
    return {
        "__meta__": {},
        "__context__": {},
        "__run_config__": {
            "ident": "alg",
            "request": request.model_dump(mode="json"),
            "project_path": None,
        },
    }


def _base_before_start(self, task_id, args, kwargs):
    # Replace kwargs with the run configuration (see Job.before_start)
    run_config = kwargs.pop("__run_config__")
    kwargs.clear()
    kwargs.update(run_config)


def _base_before_start_error(self, task_id, args, kwargs):
    kwargs.pop("__run_config__")
    raise ValueError("Invalid arguments")


def test_generic_job_without_subscriber(job: GenericJob, monkeypatch: pytest.MonkeyPatch):
    """A request without subscriber is a valid request"""
    monkeypatch.setattr(Job, "before_start", _base_before_start)

    request = JobExecute(inputs={"a": 1})
    kwargs = _task_kwargs(request)
    job.before_start("job_01", (), kwargs)

    # The whole request is kept for postrun callbacks and job details
    assert kwargs["request"] == request.model_dump(mode="json")
    assert kwargs["a"] == 1


def test_generic_job_with_subscriber(job: GenericJob, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Job, "before_start", _base_before_start)

    request = JobExecute.model_validate(
        {"inputs": {"a": 1}, "subscriber": {"failedUri": "https://foo.com/failed"}},
    )
    kwargs = _task_kwargs(request)
    job.before_start("job_01", (), kwargs)

    assert kwargs["request"]["subscriber"] == {"failedUri": "https://foo.com/failed"}
    assert kwargs["request"]["inputs"] == {"a": 1}


def test_generic_job_request_input(job: GenericJob, monkeypatch: pytest.MonkeyPatch):
    """An input named 'request' does not replace the job request"""
    monkeypatch.setattr(Job, "before_start", _base_before_start)

    request = JobExecute(inputs={"request": "foo"})
    kwargs = _task_kwargs(request)
    job.before_start("job_01", (), kwargs)

    assert kwargs["request"] == request.model_dump(mode="json")


def test_generic_job_invalid_arguments(job: GenericJob, monkeypatch: pytest.MonkeyPatch):
    """The request is kept for postrun callbacks when 'before_start' fails"""
    monkeypatch.setattr(Job, "before_start", _base_before_start_error)

    request = JobExecute.model_validate(
        {"inputs": {"a": 1}, "subscriber": {"failedUri": "https://foo.com/failed"}},
    )
    kwargs = _task_kwargs(request)
    with pytest.raises(ValueError):
        job.before_start("job_01", (), kwargs)

    assert kwargs["request"]["subscriber"] == {"failedUri": "https://foo.com/failed"}
