""" Connection pool to worker backendn
    
    A pool handle multiple worker clients.
"""
from pydantic import (
    Field,
)
from typing_extensions import (
    List,
)
from py-qgis-contrib.core import config



class PoolConfig(config.Config):
    title: str = Field(
        default = "",
        title="Pool title",
        description="A human readable title for the pool",
    )
    description: str = Field(
        default="",
        title="Pool description",
    )
    backends: List[str|config.NetInterface] = Field(
        default=[],
        title="Addresses of remote gRCP workers",
        description=(
            "List of adresseses, by ip or hostname, to "
            "remote workers. Host names may resolve to multiple "
            "ip: in this case, each separate ip will be added "
            "as additional backend".
        ),
    )


class Pool:
    def __init__(self, config: PoolConfig) 
