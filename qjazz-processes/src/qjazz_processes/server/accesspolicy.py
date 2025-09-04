from abc import abstractmethod
from typing import (
    Annotated,
    Optional,
    Protocol,
    runtime_checkable,
)

from aiohttp import web
from pydantic import (
    ImportString,
    JsonValue,
    WithJsonSchema,
)

from qjazz_contrib.core import logger
from qjazz_contrib.core.condition import assert_postcondition
from qjazz_contrib.core.config import ConfigBase, section
from qjazz_contrib.core.models import Field

from .executor import AsyncExecutor


@section("access_policy")
class AccessPolicyConfig(ConfigBase):
    """Configure access policy"""

    policy_class: Annotated[
        # XXX ImportString does not support Json schema
        ImportString,
        WithJsonSchema({"type": "string"}),
        Field(
            default="qjazz_processes.server.policies.DefaultAccessPolicy",
            validate_default=True,
            title="Access policy module",
            description="""
            The module implementing the access policy for
            processes execution.
            """,
        ),
    ]
    config: dict[str, JsonValue] = Field({})


class NoConfig(ConfigBase):
    pass


# Enable type checking from Protocol
# This allows for validating AccessPolicy instances


@runtime_checkable
class AccessPolicy(Protocol):
    Config: type[ConfigBase] = NoConfig

    executor: AsyncExecutor

    def setup(self, app: web.Application):
        return

    @abstractmethod
    def service_permission(self, request: web.Request, service: str) -> bool:
        """Check for permission to access a service"""
        ...

    @abstractmethod
    def execute_permission(
        self,
        request: web.Request,
        service: str,
        process_id: str,
        project: Optional[str] = None,
    ) -> bool:
        """Check for permission to execute a process"""
        ...

    @abstractmethod
    def get_service(self, request: web.Request) -> str:
        """Return the defined service for the request"""
        ...

    @abstractmethod
    def get_project(self, request: web.Request) -> Optional[str]:
        """Return project for therequest"""
        ...

    @property
    def prefix(self) -> str:
        """Return the prefix path"""
        return ""

    @abstractmethod
    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
        project: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> str:
        """Format a path including service paths"""
        ...


class DummyAccessPolicy(AccessPolicy):
    executor: AsyncExecutor

    def service_permission(self, request: web.Request, service: str) -> bool:
        return False

    def execute_permission(
        self,
        request: web.Request,
        service: str,
        process_id: str,
        project: Optional[str] = None,
    ) -> bool:
        return False

    def get_service(self, request: web.Request) -> str:
        """Return the defined service for the request"""
        return ""

    def get_project(self, request: web.Request) -> Optional[str]:
        """Return project for therequest"""
        return None

    @property
    def prefix(self) -> str:
        """Return the prefix path"""
        return ""

    def format_path(
        self,
        request: web.Request,
        path: str,
        service: Optional[str] = None,
        project: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> str:
        """Format a path including service paths"""
        raise NotImplementedError("Dummy policy")


def create_access_policy(
    conf: AccessPolicyConfig,
    app: web.Application,
    executor: AsyncExecutor,
) -> AccessPolicy:
    """Create access policy"""
    logger.info("Creating access policy %s", str(conf.policy_class))

    policy_class = conf.policy_class
    policy_conf = policy_class.Config.model_validate(conf.config)

    instance = policy_class(policy_conf)
    assert_postcondition(
        isinstance(instance, AccessPolicy),
        f"{instance} does no supports AccessPolicy protocol",
    )
    instance.executor = executor
    instance.setup(app)

    return instance
