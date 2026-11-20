import pytest

from pydantic import ValidationError

from qjazz_processes.processing.config import ProcessingConfig

# from qjazz_processes.processing.config import ProcessingConfig


# def test_processing_config(qgis_session: ProcessingConfig):


@pytest.mark.parametrize(
    "value,expected",
    [
        ("value", "value"),
        # Booleans are subclasses of int: they must be checked first
        (True, "true"),
        (False, "false"),
        (1, "1"),
        (0, "0"),
        (2.5, "2.5"),
    ],
)
def test_config_qgis_settings_values(value: str | bool | float, expected: str) -> None:
    """QGIS settings values are converted to strings"""
    conf = ProcessingConfig(qgis_settings={"section/key": value})

    assert conf.qgis_settings == {"section/key": expected}
    assert conf.settings()["section/key"] == expected


def test_config_qgis_settings_invalid_value() -> None:
    with pytest.raises(ValidationError, match="Unsupported type"):
        ProcessingConfig(qgis_settings={"section/key": [1, 2]})
