from pathlib import Path
from typing import (
    ClassVar,
    Optional,
    Sequence,
)

import celery
import celery.states

from pydantic import (
    DirectoryPath,
    FilePath,
    JsonValue,
    NonNegativeInt,
)

from qjazz_contrib.core.config import (
    ConfigBase,
    TLSConfig,
)
from qjazz_contrib.core.models import Field


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
        else:
            return f"{scheme}://{self.backend_host}"


class Celery(celery.Celery):
    """Celery application

    See https://docs.celeryq.dev/en/stable/reference/celery.html#celery.Celery
    """

    STATE_PENDING: ClassVar[str] = celery.states.PENDING
    STATE_FAILURE: ClassVar[str] = celery.states.FAILURE
    STATE_STARTED: ClassVar[str] = celery.states.STARTED
    STATE_SUCCESS: ClassVar[str] = celery.states.SUCCESS
    STATE_REVOKED: ClassVar[str] = celery.states.REVOKED
    STATE_UPDATED: ClassVar[str] = "UPDATED"

    FINISHED_STATES: ClassVar[Sequence[str]] = (
        celery.states.FAILURE,
        celery.states.SUCCESS,
    )

    def __init__(self, main: Optional[str], conf: Optional[CeleryConfig] = None, **kwargs):
        """Create a Celery instance from
        configuration.
        """
        conf = conf or CeleryConfig(broker_host=LOCAL_BROKER, backend_host=LOCAL_BACKEND)

        super().__init__(
            main,
            broker=conf.broker_url(),
            backend=conf.backend_url(),
            broker_connection_retry_on_startup=True,
            redis_backend_health_check_interval=5,
            result_extended=True,
            **kwargs,
        )

        # See https://docs.celeryq.dev/en/stable/userguide/configuration.html
        self.conf.result_expires = conf.result_expires
        self.conf.task_time_limit = conf.task_time_limit + conf.task_time_grace_period
        self.conf.task_soft_time_limit = conf.task_time_limit

        # Send a sent event so that tasks can be tracked
        # before beeing consumed by a worker
        self.conf.task_send_sent_event = True

        # Worker configuration

        if conf.concurrency:
            self.conf.worker_concurrency = conf.concurrency
        if conf.max_tasks_per_child:
            self.conf.worker_max_tasks_per_child = conf.max_tasks_per_child
        if conf.max_memory_per_child:
            self.conf.worker_max_memory_per_child = conf.max_memory_per_child

        # TLS configuration
        if conf.broker_use_tls:
            if conf.broker_tls:
                # https://docs.celeryq.dev/en/stable/userguide/configuration.html#broker-use-ssl
                if conf.broker_tls.cafile:
                    self.conf.broker_use_ssl = {"ca_certs": conf.broker_tls.cafile}
                if conf.broker_tls.keyfile and conf.broker_tls.certfile:
                    self.conf.broker_use_ssl.update(
                        {
                            "keyfile": conf.broker_tls.keyfile.as_posix(),
                            "certfile": conf.broker_tls.certfile.as_posix(),
                        }
                    )

            else:
                self.conf.broker_use_ssl = True

        if conf.backend_use_tls:
            import ssl

            # See https://docs.celeryq.dev/en/stable/userguide/configuration.html#broker-use-ssl
            self.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
            if conf.backend_tls:
                if conf.backend_tls.cafile:
                    self.conf.redis_backend_use_ssl.update(
                        ssl_ca_certs=conf.backend_tls.cafile,
                    )
                if conf.backend_tls.keyfile and conf.backend_tls.certfile:
                    self.conf.redis_backend_use_ssl.update(
                        ssl_keyfile=conf.backend_tls.keyfile.as_posix(),
                        ssl_certfile=conf.backend_tls.certfile.as_posix(),
                    )

        if conf.security:
            """ Configure message signing
            """
            self.conf.update(
                security_key=conf.security.keyfile.as_posix(),
                security_certificate=conf.security.certfile.as_posix(),
                security_cert_store=conf.security.cert_store.joinpath("*.pem").as_posix(),
                security_digest="sha256",
                task_serializer="auth",
                event_serializer="auth",
                accept_content=["auth"],
            )
            self.setup_security()

    def run_configs(
        self,
        destinations: Optional[Sequence[str]] = None,
        timeout: float = 1.0,
    ) -> dict[str, JsonValue]:
        """Return active worker's run configs"""
        return self.control.broadcast(
            "run_configs",
            reply=True,
            destination=destinations,
        )
