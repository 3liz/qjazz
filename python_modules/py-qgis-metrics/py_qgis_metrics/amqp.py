""" Send metrics through amqp messages
"""
import os

from amqpclient.aio import AsyncPublisher
from pika import PlainCredentials
from pydantic import BaseModel, Field, SecretStr
from typing_extensions import List, Optional, Self, TypeVar

from py_qgis_contrib.core import logger
from py_qgis_http.metrics import METRICS_HANDLER_CONTRACTID, Data, Metrics

T = TypeVar('T')


def _get_env(env: str, default: T) -> T:
    val = os.getenv(env, default)
    if default is not None:
        val = type(default)(val)
    return val


class AmqpConfig(BaseModel):
    host: str | List[str] = Field(default=_get_env('AMQP_HOST', None), validate_default=True)
    port: int = Field(default=_get_env('AMQP_PORT', 5672), validate_default=True)
    vhost: str = Field(default=_get_env('AMQP_VHOST', "/"), validate_default=True)
    user: str = Field(default=_get_env('AMQP_USER', ""), validate_default=True)
    exchange: str = Field(default=_get_env('AMQP_EXCHANGE', None), validate_default=True)
    reconnect_delay: int = Field(
        default=_get_env('AMQP_RECONNECT_DELAY', 5),
        validate_default=True,
        title="Reconnection delay is seconds",
    )
    password: Optional[SecretStr] = Field(
        default=None,
        description=(
            "If not set, look in the file given by the environment variable "
            "`AMQPPASSFILE`. The file must be structured with each line formatted "
            "as: `<vhost|*>:<user|*>:<password>`."
        ),
    )

    def get_credentials(self) -> Optional[PlainCredentials]:
        """ Get credentials  from configuration
        """
        if not self.user:
            # No user, don't bother
            return

        if self.password is not None:
            return PlainCredentials(self.user, self.password.get_secret_value())

        # Read credential from AMQPPASSFILE if it exists
        passfile = os.getenv("AMQPPASSFILE")
        if not (passfile and os.path.exists(passfile)):
            return None
        logger.debug("Using AMQP passfile: %s", passfile)
        with open(passfile) as fp:
            for line in fp.readlines():
                creds = line.strip()
                if not creds or creds.startswith('#'):
                    continue
                # Check matching vhost and user
                cr_vhost, cr_user, passwd = creds.split(':')
                if cr_vhost in ('*', self.vhost) and cr_user in ('*', self.user):
                    logger.info("Found password for  user '%s' on vhost '%s'", self.user, self.vhost)
                    return PlainCredentials(self.user, passwd)


class AmqpMetrics(Metrics):

    def __init__(self):
        self._client = None
        self._exchange = None

    async def initialize(self, **options) -> Self:
        # Validate the options
        conf = AmqpConfig.model_validate(options)

        kwargs = {}

        credentials = conf.get_credentials()
        if credentials:
            kwargs['credentials'] = credentials

        client = AsyncPublisher(
            host=conf.host,
            port=conf.port,
            virtual_host=conf.vhost,
            reconnect_delay=conf.reconnect_delay,
            logger=logger.logger(),
            **kwargs,
        )

        logger.info("AMQP: Opening connection to server '%s'  (port: %s)", conf.host, conf.port)
        await client.connect(exchange=conf.exchange, exchange_type='topic')

        self._client = client
        logger.info("AMQP metrics initialized.")

        return self

    async def emit(self, key: str, data: Data) -> None:
        self._client.publish(
            data.dump_json(),
            routing_key=key,
            expiration=3000,
            content_type="application/json",
            content_encoding="utf-8",
        )

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


# Entry point registration
def register(cm):
    cm.register_service(
        f"{METRICS_HANDLER_CONTRACTID}?name=amqp",
        AmqpMetrics(),
    )
