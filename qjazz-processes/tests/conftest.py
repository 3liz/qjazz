
from pathlib import Path

import pytest

from qjazz_cache.prelude import ProjectsConfig

# Import fixtures in local namespace
from qjazz_processes.tests.conftest import *  # noqa F401


@pytest.fixture(scope="session")
def cache_config(data: Path) -> ProjectsConfig:
    """Setup projects cache configuration"""
    return ProjectsConfig(
        trust_layer_metadata=True,
        disable_getprint=False,
        force_readonly_layers=True,
        ignore_bad_layers=True,
        search_paths={
            "/samples": f"{data}/samples/",
            "/france": f"{data}/france_parts/",
            "/montpellier": f"{data}/montpellier/",
            "/database": "postgresql://?service=qjazz",
            "/lines": f"{data}/lines/",
        },
    )
