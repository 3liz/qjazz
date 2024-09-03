import celery
import celery.states

from pydantic import (
    DirectoryPath,
    Field,
    FilePath,
    NonNegativeInt,
)
from typing_extensions import (
    ClassVar,
    Dict,
    Optional,
    Sequence,
    Tuple,
)

from py_qgis_contrib.core.config import (
    Config as BaseConfig,
)
from py_qgis_contrib.core.config import (
    SSLConfig,
)


class SecurityConfig(BaseConfig):
    """Message signing configuration"""
    cert_store: DirectoryPath
    keyfile:  FilePath
    certfile: FilePath


# Use this on local setup
LOCAL_BROKER = ""
LOCAL_BACKEND = "localhost:6379/0"


class CeleryConfig(BaseConfig):
    """Celery configuration"""
    broker_host: str = Field(default=LOCAL_BROKER, title="Celery amqp broker host")
    broker_use_ssl: bool = False
    broker_ssl: Optional[SSLConfig] = None

    backend_host: str = Field(default=LOCAL_BACKEND, title="Celery redis backend host")
    backend_use_ssl: bool = False
    backend_ssl: Optional[SSLConfig] = None

    # https://docs.celeryq.dev/en/stable/userguide/security.html
    security: Optional[SecurityConfig] = None

    # https://docs.celeryq.dev/en/stable/userguide/configuration.html

    task_time_limit: int = Field(
        default=3600,
        gt=60,
        description=(
            "Task hard time limit in seconds.\n"
            "The worker processing the task will be killed\n"
            "and replaced with a new one when this is exceeded."
        ),
    )

    task_time_grace_period: int = Field(
        default=60,
        ge=0,
        description=(
            "Grace period to add to the 'task_time_limit'\n"
            "value.\n"
            "The SoftTimeLimitExceeded exception will be raised\n"
            "when the 'task_time_limit' is exceeded."
        ),
    )

    result_expires: int = Field(
        default=86400,
        description=(
            "Time (in seconds), for when after stored task tombstones will\n"
            "be deleted"
        ),
    )

    concurrency: Optional[int] = Field(
        default=None,
        ge=1,
        title="Concurrency",
        description=(
            "The number of concurrent worker processes executing tasks."
        ),
    )

    max_tasks_per_child: Optional[int] = Field(
        default=None,
        ge=1,
        title="Processes life cycle",
        description=(
            "Maximum number of tasks a pool worker process can execute\n"
            "before it's replaced with a new one. Default is no limit."
        ),
    )

    max_memory_per_child: Optional[int] = Field(
        default=None,
        title="Maximum consumed memory",
        description=(
            "Maximum amount of resident memory, in kilobytes,\n"
            "that may be consumed by a worker before it will\n"
            "be replaced by a new worker."
        ),
    )

    # Enable autoscaling
    autoscale: Optional[Tuple[NonNegativeInt, NonNegativeInt]] = Field(
        default=None,
        title="Autoscale",
        description="Activate concurrency autoscaling",
    )


class Celery(celery.Celery):
    """ Celery application

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
        """ Create a Celery instance from
            configuration.
        """
        conf = conf or CeleryConfig(broker_host=LOCAL_BROKER, backend_host=LOCAL_BACKEND)

        super().__init__(
            main,
            broker=f"amqp://{conf.broker_host}",
            backend=f"rediss://{conf.backend_host}"
                if conf.backend_use_ssl
                else f"redis://{conf.backend_host}",
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

        # SSL configuration

        if conf.broker_use_ssl:
            if conf.broker_ssl:
                # https://docs.celeryq.dev/en/stable/userguide/configuration.html#broker-use-ssl
                if conf.broker_ssl.cafile:
                    self.conf.broker_use_ssl = {'ca_certs': conf.broker_ssl.cafile}
                if conf.broker_ssl.keyfile and conf.broker_ssl.certfile:
                    self.conf.broker_use_ssl.update({
                        'keyfile':  conf.broker_ssl.keyfile.as_posix(),
                        'certfile': conf.broker_ssl.certfile.as_posix(),
                    })

            else:
                self.conf.broker_use_ssl = True

        if conf.backend_use_ssl:
            import ssl
            # See https://docs.celeryq.dev/en/stable/userguide/configuration.html#broker-use-ssl
            self.conf.redis_backend_use_ssl = {'ssl_cert_reqs': ssl.CERT_REQUIRED}
            if conf.backend_ssl:
                if conf.backend_ssl.cafile:
                    self.conf.redis_backend_use_ssl.update(
                        ssl_ca_certs=conf.backend_ssl.cafile,
                    )
                if conf.backend_ssl.keyfile and conf.backend_ssl.certfile:
                    self.conf.redis_backend_use_ssl.update(
                        ssl_keyfile=conf.backend_ssl.keyfile.as_posix(),
                        ssl_certfile=conf.backend_ssl.certfile.as_posix(),
                    )

        if conf.security:
            """ Configure message signing
            """
            self.conf.update(
                security_key=conf.security.keyfile.as_posix(),
                security_certificate=conf.security.certfile.as_posix(),
                security_cert_store=conf.security.cert_store.joinpath('*.pem').as_posix(),
                security_digest='sha256',
                task_serializer='auth',
                event_serializer='auth',
                accept_content=['auth'],
            )
            self.setup_security()

    def run_configs(self, destinations: Optional[Sequence[str]] = None) -> Sequence[Dict]:
        """ Return active worker's run configs
        """
        return self.control.broadcast(
            '_run_configs',
            reply=True,
            destination=destinations,
        )
