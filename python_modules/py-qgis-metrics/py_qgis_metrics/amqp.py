""" Send metrics through amqp messages
"""
import os

from amqpclient.aio import AsyncPublisher
from pika import PlainCredentials
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import List, Optional, Self, Type

from py_qgis_contrib.core import logger
from py_qgis_http.metrics import METRICS_HANDLER_CONTRACTID, Data, Metrics


class AmqpConfig(BaseSettings, env_prefix='AMQP_'):

    host: str | List[str]
    port: int = Field(default=5672)
    vhost: str = Field(default="/")
    user: str = Field(default="")
    exchange: str
    reconnect_delay: int = Field(
        default=5,
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
            return None

        if self.password is not None:
            return PlainCredentials(self.user, self.password.get_secret_value())

        creds: Optional[PlainCredentials] = None

        # Read credential from AMQPPASSFILE if it exists
        passfile = os.getenv("AMQPPASSFILE")
        if not (passfile and os.path.exists(passfile)):
            logger.warning("AMQPASSFILE is set but file does not exists.")
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
                    creds = PlainCredentials(self.user, passwd)
                    break
        return creds
        

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

    async def close(self):
        if self._client:
            self._client.close()
            self._client = None


# Entry point registration
def register(cm):
    cm.register_service(
        f"{METRICS_HANDLER_CONTRACTID}?name=amqp",
        AmqpMetrics(),
    )
