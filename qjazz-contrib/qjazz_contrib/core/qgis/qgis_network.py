#
# Copyright 2025 3liz
#
""" Utilities for qgis network inspection and
    settings
"""

from typing import (
    Literal,
    Optional,
    assert_never,
)

from pydantic import (
    NonNegativeInt,
)

from qgis.core import (
    QgsNetworkAccessManager,
    QgsNetworkReplyContent,
    QgsNetworkRequestParameters,
)
from qgis.PyQt.QtNetwork import (
    QNetworkReply,
    QNetworkRequest,
)

from .. import config, logger
from ..models import Field

CachePolicy = Literal[
    'always_network',
    'prefer_network',
    'prefer_cache',
    'alway_cache',
]



class RequestPolicy(config.ConfigBase):
    cache_policy: Optional[CachePolicy] = Field(
        default=None,
        title="Cache load control",
        description="Override QNetworkRequest::CacheLoadControl for request.",
    )
    transfer_timeout: Optional[NonNegativeInt] = Field(
        default=None,
        title="Transfer timeout in ms",
    )

    @staticmethod
    def set_request_cache_policy(request: QNetworkRequest, policy: CachePolicy):
        request.setAttribute(
            QNetworkRequest.CacheLoadControlAttribute,
            RequestPolicy.cache_policy_to_load_control(policy),
        )

    @staticmethod
    def cache_policy_to_load_control(policy: CachePolicy) -> QNetworkRequest.CacheLoadControl:
        match policy:
            case 'always_network':
                return QNetworkRequest.CacheLoadControl.AlwaysNetwork
            case 'prefer_network':
                return QNetworkRequest.CacheLoadControl.PreferNetwork
            case 'prefer_cache':
                return QNetworkRequest.CacheLoadControl.PreferCache
            case 'alway_cache':
                return QNetworkRequest.CacheLoadControl.AlwaysCache
            case _ as unreachable:
                assert_never(unreachable)

    def process_request(self, request: QNetworkRequest):
        if self.transfer_timeout is not None:
            request.setTransferTimeout(self.transfer_timeout)
        if self.cache_policy is not None:
            self.set_request_cache_policy(request, self.cache_policy)


class QgisNetworkConfig(config.ConfigBase):
    transfer_timeout: NonNegativeInt = Field(
        default=10000,
        title="Transfer timeout in ms",
        description="""
            Transfers are aborted if no bytes are transferred before
            the timeout expires.
            If set to 0, the timeout is disobled.
            Default value is set to 10000 milliseconds.
        """,
    )
    trace: bool = Field(
        False,
        title="Trace network activity",
    )
    cache_policy: Optional[CachePolicy] = Field(
        default=None,
        title="Global cache policy",
        description="""
            Set a global cache policy for all requests"
            If set, this will override requests cache policy".
        """,
    )
    domain_policy: dict[str, RequestPolicy] = Field(
        default={},
        title="Domain policies",
        description="Set per domain policy",
    )

    def process_request(self, request: QNetworkRequest):
        if self.domain_policy:
            policy = self.domain_policy.get(request.url().host())
            if policy:
                policy.process_request(request)
        elif self.cache_policy:
            RequestPolicy.set_request_cache_policy(request, self.cache_policy)

    def configure_network(self):

        nam = QgsNetworkAccessManager.instance()

        if not nam.isStrictTransportSecurityEnabled():
            # QGIS enable strict transport security by default
            logger.warning("NET: Strict transport security is DISABLED")

        logger.info("NET: setting transfer timeout to %s ms", self.transfer_timeout)
        nam.setTransferTimeout(self.transfer_timeout)

        if self.trace:
            # XXX signals requestCreated or requestAbountToBeCreated
            # segfault whenever trying to connect a Python method.
            logger.info("NET: trace is ON")
            nam.requestCreated.connect(on_request_created)
            nam.finished.connect(on_reply_finished)

        if self.cache_policy or self.domain_policy:
            def process_request(request: QNetworkRequest):
                self.process_request(request)

            nam.setRequestPreprocessor(process_request)

#
# Hooks
#
def on_request_created(params: QgsNetworkRequestParameters):
    logger.info("NET: Request[%s] created: %s",
        params.requestId(),
        params.request().url().toDisplayString(),
    )

def on_reply_finished(reply: QgsNetworkReplyContent):
    """ Run whenever a pending network reply is finished.
    """
    err = reply.error()
    status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
    url: str = reply.request().url().toDisplayString()
    if err != QNetworkReply.NoError:
        logger.error(
            "NET: Request[%s] finished with error:  %s: %s <http status: %s>",
            reply.requestId(),
            url,
            reply.errorString(),
            status,
        )
    else:
        logger.info(
            "NET: Request[%s] finished: %s <http status: %s>",
            reply.requestId(),
            url,
            status,
        )

