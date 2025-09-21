from pydantic import Field

from qjazz_core import config


def setup_module() -> None:
    """Setup config model"""

    class SubConfig(config.ConfigBase):
        bar: str = "Hello"

    @config.section("test1")
    class Test1(config.ConfigBase):
        foo: bool = False
        sub: SubConfig = SubConfig()

    builder = config.ConfBuilder()

    assert "test1" in builder._global_sections


def test_config_default() -> None:
    """Test config with default settings"""
    builder = config.ConfBuilder()
    builder.validate({})
    test = builder.conf.test1  # type: ignore [attr-defined]
    assert test.foo == False  # noqa
    assert test.sub.bar == "Hello"


def test_config_validate() -> None:
    """Test config with default settings"""
    builder = config.ConfBuilder()
    builder.validate({"test1": {"foo": True, "sub": {"bar": "World"}}})
    test = builder.conf.test1  # type: ignore [attr-defined]
    assert test.foo == True  # noqa
    assert test.sub.bar == "World"


def test_config_update() -> None:
    """Test updating service"""
    builder = config.ConfBuilder()
    builder.validate({})

    class Sub(config.ConfigBase):
        alpha: int = 0
        beta: int = 0

    class Test(config.ConfigBase):
        foo: int = 2
        bar: Sub = Sub()
        simple_list: list[str] = Field(["a", "b"])
        simple_dict: dict[str, int] = Field(
            {
                "a": 1,
                "b": 2,
            }
        )

    builder.add_section("test", Test)
    assert builder._model_changed

    test = builder.conf.test  # type: ignore [attr-defined]
    assert test.foo == 2
    assert test.bar.alpha == 0
    assert test.bar.beta == 0
    assert test.simple_list == ["a", "b"]
    assert test.simple_dict == {"a": 1, "b": 2}

    # Check partial update

    # Test updating actual config
    builder.update_config(
        {
            "test": {
                "foo": 3,
                "bar": {"alpha": 1},
                "simple_list": ["c", "d"],
                "simple_dict": {"c": "2"},
            },
        },
    )

    test = builder.conf.test  # type: ignore [attr-defined]
    assert test.foo == 3
    assert test.bar.alpha == 1
    assert test.bar.beta == 0
    assert test.simple_list == ["c", "d"]
    assert test.simple_dict == {"c": 2}


def test_config_proxy() -> None:
    """Test configuration proxy"""
    builder = config.ConfBuilder()
    builder.validate({})

    proxy = config.ConfigProxy(builder, "test1.sub") # type: ignore [var-annotated]
    assert proxy.bar == "Hello"

    builder.validate({"test1": {"sub": {"bar": "World"}}})
    # Check that new config is reflected
    assert proxy.bar == "World"
