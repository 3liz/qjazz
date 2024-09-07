""" Send metrics through amqp messages
"""
import os

from aiohttp import web
from amqpclient.aio import AsyncPublisher
from pika import PlainCredentials
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings
from typing_extensions import List, Optional

from py_qgis_contrib.core import logger

from ..channel import Channel
from ._metrics import Data, Metrics


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

    routing_key: str = Field(
        title="Routing key",
        description=(
            "The routing key for the metric message\n"
            "This key is passed to monitoring backend.\n"
        ),
    )


class AmqpMetrics(Metrics):

    Config = AmqpConfig

    def __init__(self, conf: AmqpConfig):

        kwargs = {}

        credentials = conf.get_credentials()
        if credentials:
            kwargs['credentials'] = credentials

        self._routing_key = conf.routing_key
        self._exchange = conf.exchange
        self._client = AsyncPublisher(
            host=conf.host,
            port=conf.port,
            virtual_host=conf.vhost,
            reconnect_delay=conf.reconnect_delay,
            logger=logger.logger(),
            **kwargs,
        )

        logger.info("AMQP:  connection to server '%s'  (port: %s)", conf.host, conf.port)

    async def setup(self) -> None:
        await self._client.connect(exchange=self._exchange, exchange_type='topic')
        logger.info("AMQP metrics initialized.")

    async def emit(self, request: web.Request, chan: Channel, data: Data):
        self._client.publish(
            data.dump_json(),
            routing_key=self._routing_key,
            expiration=3000,
            content_type="application/json",
            content_encoding="utf-8",
        )

    async def close(self):
        if self._client:
            self._client.close()
            self._client = None
