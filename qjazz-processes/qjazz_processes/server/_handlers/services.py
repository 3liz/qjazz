from typing import (
    Optional,
    Protocol,
    Self,
    Sequence,
)

from aiohttp import web
from pydantic import Field

from .protos import (
    HandlerProto,
    Link,
    PresenceDetails,
    make_link,
    swagger,
)


class PathFormatter(Protocol):
    def __call__(self, request: web.Request, path: str, service: Optional[str] = None) -> str: ...


class ServiceItem(swagger.JsonModel):
    name: str
    title: str = Field("")
    description: str = Field("")
    qgis_version_info: int
    version_details: str | Sequence[str]
    callbacks: Sequence[str]
    links: Sequence[Link]

    @classmethod
    def from_details(
        cls,
        request: web.Request,
        details: PresenceDetails,
        format_path: PathFormatter,
    ) -> Self:
        links = [link for link in details.links]
        links.extend(
            (
                make_link(
                    request,
                    rel="http://www.opengis.net/def/rel/ogc/1.0/processes",
                    path=format_path(request, "/processes/", service=details.service),
                    title="Services processes",
                ),
                make_link(
                    request,
                    rel="http://www.opengis.net/def/rel/ogc/1.0/job-list",
                    path=format_path(request, "/jobs/", service=details.service),
                    title="Job list",
                ),
            )
        )
        return cls(
            name=details.service,
            title=details.title,
            description=details.description,
            qgis_version_info=details.qgis_version_info,
            version_details=details.versions,
            callbacks=details.callbacks,
            links=links,
        )


@swagger.model
class ServicesResponse(swagger.JsonModel):
    services: list[ServiceItem]


class Services(HandlerProto):
    async def list_services(self, request: web.Request) -> web.Response:
        """
        summary: "Return availables services"
        description: >
            Returns a list of available services.
        tags:
            - services
        responses:
            "200":
                description: >
                    Returns the list of available services
                content:
                    application/json:
                        schema:
                            $ref: '#definitions/ServicesResponse'
        """
        return web.Response(
            content_type="application/json",
            text=ServicesResponse(
                services=[
                    ServiceItem.from_details(
                        request,
                        details,
                        self.format_path,
                    )
                    for details in self._executor.services
                    if self._accesspolicy.service_permission(request, details.service)
                ],
            ).model_dump_json(),
        )
