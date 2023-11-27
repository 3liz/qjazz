import pytest

from py_qgis_contrib.core import componentmanager as cm
from py_qgis_http.metrics import (  # noqa
    METRICS_HANDLER_CONTRACTID,
    METRICS_HANDLER_ENTRYPOINTS,
    Data,
    Metrics,
)
from py_qgis_metrics.amqp import AmqpConfig, AmqpMetrics

pytest_plugins = ('pytest_asyncio',)

amqp_options = {
    "host": "amqp",
    "exchange": "amqp.tests",
}


def test_validate_options():
    """ Test options validations
    """
    options = AmqpConfig.model_validate(amqp_options)
    assert options.host == amqp_options['host']
    assert options.exchange == amqp_options['exchange']


def test_entrypoint():
    """  Test that the service factory is correctly registered
    """
    cm.load_entrypoint(METRICS_HANDLER_ENTRYPOINTS, "amqp")

    service = cm.get_service(f"{METRICS_HANDLER_CONTRACTID}?name=amqp")
    assert service is not None


@pytest.mark.amqp
async def test_emit_data():
    """ Teste emit data to RMQ server
    """
    service = AmqpMetrics()
    await service.initialize(**amqp_options)
    await service.emit(
        "local.amqp.tests",
        Data(
            status=200,
            service="WFS",
            request="GetCapabilities",
            project="foobar",
            memory_footprint=0,
            response_time=0,
            latency=0,
            cached=True,
        ),
    )
