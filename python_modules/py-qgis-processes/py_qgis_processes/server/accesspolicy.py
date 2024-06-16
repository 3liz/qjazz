
from abc import ABC, abstractmethod

from aiohttp import web
from pydantic import (
    Field,
    ImportString,
    JsonValue,
    WithJsonSchema,
)
from typing_extensions import (
    Annotated,
    Dict,
    Optional,
    Type,
)

from py_qgis_contrib.core import logger
from py_qgis_contrib.core.config import ConfigBase, section

from ..executor import Executor


@section("access_policy")
class AccessPolicyConfig(ConfigBase):
    """Configure access policy"""
    policy_class: Annotated[
        # XXX ImportString does not support Json schema
        ImportString,
        WithJsonSchema({'type': 'string'}),
        Field(
            default="py_qgis_processes.server.policies.DefaultAccessPolicy",
            validate_default=True,
            title="Access policy module",
            description=(
                "The module implementing the access policy for\n"
                "processes execution."
            ),
        ),
    ]
    config: Dict[str, JsonValue] = Field({})


class NoConfig(ConfigBase):
    pass


class AccessPolicy(ABC):

    Config: Type[ConfigBase] = NoConfig

    _executor: Executor

    def setup(self, app: web.Application):
        pass

    @abstractmethod
    def service_permission(self, request: web.Request, service: str) -> bool:
        """ Check for permission to access a service
        """
        ...

    @abstractmethod
    def execute_permission(
        self,
        request: web.Request,
        service: str,
        process_id: str,
        project: Optional[str] = None,
    ) -> bool:
        """ Check for permission to execute a process
        """
        ...

    @abstractmethod
    def get_service(self, request: web.Request) -> str:
        """ Return the defined service for the request
        """
        ...

    @abstractmethod
    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
    ) -> str:
        """ Format a path including service paths
        """
        ...


def create_access_policy(
    conf: AccessPolicyConfig,
    app: web.Application,
    executor: Executor,
) -> AccessPolicy:
    """  Create access policy
    """
    logger.info("Creating access policy %s", str(conf.policy_class))

    policy_class = conf.policy_class
    policy_conf = policy_class.Config.model_validate(conf.config)

    instance = conf.policy_class(policy_conf)
    instance._executor = executor

    instance.setup(app)

    return instance
