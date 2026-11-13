"""Celery configuration"""

from pathlib import Path
from typing import (
    Optional,
)

from pydantic import (
    DirectoryPath,
    FilePath,
    NonNegativeInt,
)

from qjazz_core.config import (
    ConfigBase,
    TLSConfig,
)
from qjazz_core.models import Field


class SecurityConfig(ConfigBase):
    """Message signing configuration"""

    cert_store: DirectoryPath
    keyfile: FilePath
    certfile: FilePath


# Use this on local setup
LOCAL_BROKER = "localhost"
LOCAL_BACKEND = "localhost:6379/0"


class CeleryScheduler(ConfigBase):
    """Scheduler configuration"""

    enabled: bool = Field(
        default=False,
        title="Enable scheduler",
        description="""
        Enable embedded scheduler.
        Prefer scheduler as a service if more
        than one worker node is used.
        """,
    )
    max_interval: Optional[int] = Field(
        default=None,
        title="Max interval",
        description="Max seconds to sleep between schedule iterations.",
    )
    # NOTE: Celery scheduler database use a shelve db
    # to store schedule info
    # See https://docs.python.org/3/library/shelve.html
    database: Optional[Path] = Field(
        default=None,
        title="Scheduler database path",
        description="""
        Path to the schedule database.
        Defaults to `celerybeat-schedule` (from Celery doc).
        """,
    )

    def database_filename(self) -> Optional[str]:
        return str(self.database) if self.database else None


class CeleryConfig(ConfigBase):
    """Celery configuration"""

    broker_host: str = Field(
        default=LOCAL_BROKER,
        title="Celery amqp broker host",
        min_length=1,
    )
    broker_use_tls: bool = False
    broker_user: Optional[str] = None
    broker_password: Optional[str] = None
    broker_tls: Optional[TLSConfig] = None

    backend_host: str = Field(default=LOCAL_BACKEND, title="Celery redis backend host")
    backend_use_tls: bool = False
    backend_password: Optional[str] = None
    backend_tls: Optional[TLSConfig] = None

    # https://docs.celeryq.dev/en/stable/userguide/security.html
    security: Optional[SecurityConfig] = None

    # https://docs.celeryq.dev/en/stable/userguide/configuration.html

    task_time_limit: int = Field(
        default=3600,
        gt=60,
        description="""
        Task hard time limit in seconds.
        The worker processing the task will be killed
        and replaced with a new one when this is exceeded.
        """,
    )

    task_time_grace_period: int = Field(
        default=60,
        ge=0,
        description="""
        Grace period to add to the 'task_time_limit' value.
        The SoftTimeLimitExceeded exception will be raised
        when the 'task_time_limit' is exceeded.
        """,
    )

    result_expires: int = Field(
        default=86400,
        description="""
        Time (in seconds), for when after stored task tombstones will
        be deleted
        """,
    )

    concurrency: Optional[int] = Field(
        default=None,
        ge=1,
        title="Concurrency",
        description="The number of concurrent worker processes executing tasks.",
    )

    # Enable autoscaling
    max_concurrency: Optional[NonNegativeInt] = Field(
        default=None,
        title="Autoscale",
        description="Activate concurrency autoscaling",
    )

    max_tasks_per_child: Optional[int] = Field(
        default=None,
        ge=1,
        title="Processes life cycle",
        description="""
        Maximum number of tasks a pool worker process can execute
        before it's replaced with a new one. Default is no limit.
        """,
    )

    max_memory_per_child: Optional[int] = Field(
        default=None,
        title="Maximum consumed memory",
        description="""
        Maximum amount of resident memory, in kilobytes,
        that may be consumed by a worker before it will
        be replaced by a new worker.
        """,
    )

    # Scheduler
    scheduler: CeleryScheduler = Field(default=CeleryScheduler())

    def broker_url(self) -> str:
        match (self.broker_user, self.broker_password):
            case (str(name), str(passwd)):
                return f"amqp://{name}:{passwd}@{self.broker_host}"
            case (str(name), None):
                return f"amqp://{name}@{self.broker_host}"
            case _:
                return f"amqp://{self.broker_host}"

    def backend_url(self) -> str:
        scheme = "rediss" if self.backend_use_tls else "redis"
        if self.backend_password:
            return f"{scheme}://:{self.backend_password}@{self.backend_host}"
        return f"{scheme}://{self.backend_host}"
