from typing import (
    TYPE_CHECKING,
    Callable,
    Optional,
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

if TYPE_CHECKING:
    from mypy_extensions import DefaultNamedArg

    PathFormatter = Callable[[web.Request, str, DefaultNamedArg(Optional[str], "service")], str]
else:
    PathFormatter = Callable[[web.Request, str, str], str]


class ServiceItem(swagger.JsonModel):
    name: str
    title: str = Field("")
    description: str = Field("")
    qgis_version_info: int
    version_details: str
    links: Sequence[Link]

    @classmethod
    def from_details(
        cls,
        request: web.Request,
        details: PresenceDetails,
        format_path: PathFormatter,
    ) -> Self:
        links = [link for link in details.links]
        links.append(
            make_link(
                request,
                rel="related",
                path=format_path(request, "/processes/", service=details.service),
                title="Services processes",
            ),
        )
        return cls(
            name=details.service,
            title=details.title,
            description=details.description,
            qgis_version_info=details.qgis_version_info,
            version_details=details.versions,
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
