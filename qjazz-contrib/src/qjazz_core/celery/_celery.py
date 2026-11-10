from typing import (
    ClassVar,
    Optional,
    Sequence,
)

import celery
import celery.states

from .config import (
    LOCAL_BACKEND,
    LOCAL_BROKER,
    CeleryConfig,
)


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

        # Declare queues as priority queues (x-max-priority), otherwise
        # RabbitMQ ignores task priorities (0-9).
        # Note: RabbitMQ refuses to redeclare an existing queue with
        # different arguments: existing queues must be deleted (or migrated)
        self.conf.task_queue_max_priority = 10

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
