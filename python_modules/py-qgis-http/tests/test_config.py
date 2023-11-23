
import pydantic

from py_qgis_http.config import ConfigService, add_configuration_sections
from py_qgis_http.resolver import NetAddress

try:
    # Python 3.11+
    import tomllib as toml
except ModuleNotFoundError:
    import tomli as toml


CONFIG = """
[http]
listen=["127.0.0.1", 8080]

[backends.test]
title = "Test backend"
description = "Backend for local test: run `dc up -d scale worker=<scale>`"
address = ["tcp://worker", 23456]
route = "/test"

#forward_headers = ['x-qgis-*', 'x-lizmap-*']

# Allow direct path resolution
#allow_direct_resolution = false

# WFS/GetFeature limit
getfeature_limit = 1000

# Api endpoints
[[backends.test.api]]
endpoint = "features"
delegate_to = "wfs3"
name = "Features OGC Api (WFS3)"
"""


def test_validate_netaddress():

    class _Conf(pydantic.BaseModel):
        addr: NetAddress

    def _validate(obj) -> NetAddress:
        return _Conf.model_validate(obj).addr

    assert _validate({'addr': ["localhost", 12345]}) == ("localhost", 12345)
    assert _validate({'addr': ["tcp://localhost", 12345]}) == ("localhost", 12345)


def test_validate_config():
    confservice = ConfigService()
    add_configuration_sections(confservice)

    conf = toml.loads(CONFIG)
    confservice.validate(conf)

    conf = confservice.conf
    assert 'test' in conf.backends
    assert conf.backends['test'].address == ('worker', 23456)
    assert conf.backends['test'].route.as_posix() == "/test"
    assert len(conf.backends['test'].api) == 1

    api = conf.backends['test'].api[0]
    assert api.endpoint == "features"
    assert api.delegate_to == "wfs3"
