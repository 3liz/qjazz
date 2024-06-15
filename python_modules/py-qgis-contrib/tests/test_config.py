
from typing import Dict, List

from pydantic import Field

from py_qgis_contrib.core import config

confservice = config.ConfigService()


def setup_module():
    """ Setup config model
    """
    class SubConfig(config.Config):
        bar: str = "Hello"

    @config.section('test1', confservice)
    class Test1(config.Config):
        foo: bool = False
        sub: SubConfig = SubConfig()


def test_config_default():
    """ Test config with default settings
    """
    confservice.validate({})
    test = confservice.conf.test1
    assert test.foo == False  # noqa
    assert test.sub.bar == "Hello"


def test_config_validate():
    """ Test config with default settings
    """
    confservice.validate({'test1': {'foo': True, 'sub': {'bar': "World"}}})
    test = confservice.conf.test1
    assert test.foo == True  # noqa
    assert test.sub.bar == "World"


def test_config_update():
    """ Test updating service
    """
    confservice = config.ConfigService()
    confservice.validate({})

    class Sub(config.Config):
        alpha: int = 0
        beta: int = 0

    class Test(config.Config):
        foo: int = 2
        bar: Sub = Sub()
        simple_list: List[str] = Field(['a', 'b'])
        simple_dict: Dict[str, int] = Field({
            'a': 1,
            'b': 2,
        })

    confservice.add_section('test', Test)
    assert confservice._model_changed

    test = confservice.conf.test
    assert test.foo == 2
    assert test.bar.alpha == 0
    assert test.bar.beta == 0
    assert test.simple_list == ['a', 'b']
    assert test.simple_dict == {'a': 1, 'b': 2}

    # Check partial update

    # Test updating actual config
    confservice.update_config(
        {
            'test': {
                'foo': 3,
                'bar': {'alpha': 1},
                'simple_list':  ['c', 'd'],
                'simple_dict':  {'c': '2'},
            },
        },
    )

    test = confservice.conf.test
    assert test.foo == 3
    assert test.bar.alpha == 1
    assert test.bar.beta == 0
    assert test.simple_list == ['c', 'd']
    assert test.simple_dict == {'c': 2}


def test_config_proxy():
    """ Test configuration proxy
    """
    confservice.validate({})

    proxy = config.ConfigProxy('test1.sub', _confservice=confservice)
    assert proxy.bar == "Hello"

    confservice.validate({'test1': {'sub':  {"bar": "World"}}})
    # Check that new config is reflected
    assert proxy.bar == "World"
