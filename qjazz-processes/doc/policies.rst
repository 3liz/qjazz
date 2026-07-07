.. _access_policies:

Access policies
===============

Access policies control:

- Which services a request can access
- Which processes a user can execute
- How services and projects are resolved from requests
- How URLs are formatted for process links

Implementing custom access policies
-----------------------------------

Custom access policies may be implemented from external modules.

You may configure custom policies from the [access_policy] section of the
server configuration:

    .. code-block:: toml

      [access_policy]
      #
      # Access policy module
      #
      # The module implementing the access policy for
      # processes execution.
      # 
      policy_class = "mymodule.MyAccessPolicy"
      
      # The configuration of the custom policies in TOML
      # format
      [accesspolicy.config]


AccessPolicy Protocol
---------------------

The ``policy_class`` must be an import string pointing to a class implementing the ``AccessPolicy`` protocol:


Class Attributes
~~~~~~~~~~~~~~~~

``Config``: ``type[ConfigBase]``
    A Pydantic model class for configuration. Defaults to ``NoConfig``.

    The configuration will be validated against this model.

``executor``: ``AsyncExecutor``
    Set automatically by the framework. Provides access to available services.

Methods
~~~~~~~

``setup(app: web.Application) -> None``
    Called when the policy is initialized. Use to set up any resources.

    *Default*: No-op.

``service_permission(request: aiohttp.web.Request, service: str) -> bool``
    Check if the request has permission to access the specified service.

``execute_permission(request: web.Request, service: str, process_id: str, project: Optional[str] -> bool``
    Check if the request has permission to execute the given process.

``get_service(request: aiohttp.web.Request) -> str``
    Resolve and return the service identifier for the request.
    Called when a request requires service resolution.

``get_project(request: aiohttp.web.Request) -> Optional[str]``
    Resolve and return the project (QGIS project path) for the request.
    Returns ``None`` if no project is specified.

``prefix: str`` (property)
    URL prefix for the policy. Used in path formatting.

    *Default*: Empty string.

``format_path(request: aiohttp.web.Request, path: str, service: Optional[str] = None, project: Optional[str] = None, *, query: Optional[str] = None) -> str``
    Format a complete URL including service and project parameters.
    Used to generate process links in API responses.

Implementing a Custom Policy
-----------------------------

1. Create a Python package with your policy class:

   .. code:: python

       # my_policy/__init__.py
       from my_policy.config import MyPolicyConfig
       from my_policy.policy import MyAccessPolicy

2. Define a configuration model:

   .. code:: python

       # my_policy/config.py
       from qjazz_core.config import ConfigBase
       from qjazz_core.models import Field


       class MyPolicyConfig(ConfigBase):
           allowed_services: list[str] = Field(
               default=[],
               description="List of allowed service names",
           )

3. Implement the policy class:

   .. code:: python

       # my_policy/policy.py
       from typing import Optional
       from aiohttp import web
       from qjazz_processes.server.accesspolicy import AccessPolicy
       from qjazz_core.config import ConfigBase


       class MyAccessPolicy(AccessPolicy):
           Config = MyPolicyConfig

           def __init__(self, conf: MyPolicyConfig):
               self._allowed = set(conf.allowed_services)

           def setup(self, app: web.Application):
               # Initialize resources if needed
               pass

           def service_permission(self, request: web.Request, service: str) -> bool:
               return service in self._allowed

           def execute_permission(
               self,
               request: web.Request,
               service: str,
               process_id: str,
               project: Optional[str] = None,
           ) -> bool:
               # Add custom logic (e.g., check user permissions)
               return True

           def get_service(self, request: web.Request) -> str:
               return request.query.get("service", "")

           def get_project(self, request: web.Request) -> Optional[str]:
               return request.query.get("map")

           @property
           def prefix(self) -> str:
               return "/custom"

           def format_path(
               self,
               request: web.Request,
               path: str,
               service: Optional[str] = None,
               project: Optional[str] = None,
               *,
               query: Optional[str] = None,
           ) -> str:
               # Build URL with custom logic
               return f"{self.prefix}{path}?service={service}&map={project}"

4. Configure the policy in your server settings:

   .. code-block:: toml

      [access_policy]
      policy_class = "my_policy.policy.MyAccessPolicy"
      
      [accesspolicy.config]
      allowed_services = ["wfs", "wms"]
