from typing import (
    Optional,
    Sequence,
)

from aiohttp import web
from qjazz_core.config import ConfigBase
from qjazz_core.models import Field

from ..accesspolicy import AccessPolicy
from ..models import ErrorResponse


#
#  Default acces policy
#
class DefaultAccessPolicyConfig(ConfigBase):
    service_order: Sequence[str] = Field(
        default=(),
        description="""
        Set the order of services resolution.
        Services will be picked in the order
        of the list; the first available service
        will be choosen.
        If no services are defined then a service will
        be picked from the available services.
        """,
    )


class DefaultAccessPolicy(AccessPolicy):
    """Default access policy

    The default access policy select services from request
    query 'service' parameter.
    If no parameter is present, the service is determined from
    availables services with an optional priority order.
    """

    Config = DefaultAccessPolicyConfig

    def __init__(self, conf: DefaultAccessPolicyConfig):
        self._service_order = conf.service_order

    def service_permission(self, request: web.Request, service: str) -> bool:
        return True

    def execute_permission(
        self,
        request: web.Request,
        service: str,
        process_id: str,
        project: Optional[str] = None,
    ) -> bool:
        return True

    def get_service(self, request: web.Request) -> str:
        """Return the defined service for the request"""
        service = request.query.get("service")
        if not service:
            for service in self._service_order:
                if self.executor.known_service(service):
                    break
            else:
                # Return the first available service
                if self.executor.num_services <= 1:
                    for detail in self.executor.services:
                        service = detail.service
                        break
                    else:
                        ErrorResponse.raises(web.HTTPServiceUnavailable, "No service available")
                else:
                    ErrorResponse.raises(web.HTTPBadRequest, "Service required")

        return service

    def get_project(self, request: web.Request) -> Optional[str]:
        """Return the project path (map)"""
        return request.query.get("map") or request.query.get("MAP")

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
        if service:
            service = f"service={service}"
        if project:
            project = f"map={project}"

        query = "&".join(p for p in (query, service, project) if p)
        return f"{path}?{query}" if query else path
