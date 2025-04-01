from typing import (
    Sequence,
)

from aiohttp import web

from .protos import (
    HandlerProto,
    Link,
    make_link,
    swagger,
)


@swagger.model
class Conformance(swagger.JsonModel):
    conforms_to: Sequence[str] = [
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/core",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/ogc-process-description",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/json",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/oas30",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/job-list",
        "http://www.opengis.net/spec/ogcapi-processes-1/1.0/req/dismiss",
    ]


@swagger.model
class LandingPageModel(swagger.JsonModel):
    links: Sequence[Link]


class LandingPage(HandlerProto):

    async def conformance(self, request: web.Request) -> web.Response:
        """
        summary: "Conformances classes"
        description: >
            The list of conformance classes
        tags:
            - api
        responses:
            "200":
                description: >
                    Returns the list of conformance classes
                content:
                    application/json:
                        schema:
                            $ref: '#definitions/Conformance'
        """
        return web.Response(
            content_type="application/json",
            text=Conformance().model_dump_json(),
        )

    async def landing_page(self, request: web.Request) -> web.Response:
        """
        summary: "Landing page"
        description: >
            Landing page for Qjazz processes api
        tags:
            - api
        responses:
            "200":
                description: >
                    Returns the Landing page data as JSon
                content:
                    application/json:
                        schema:
                            $ref: '#definitions/LandingPageModel'
        """
        links = [
            make_link(
                request,
                path=self.format_path(request, "/services"),
                rel="api-catalog",
                title="Available services",
            ),
            make_link(
                request,
                path=self.format_path(request, "/api"),
                rel="service-desc",
                title="Api description",
            ),
            make_link(
                request,
                path=self.format_path(request, "/conformance"),
                rel="http://www.opengis.net/def/rel/ogc/1.0/conformance",
                title="Conformance classes",
            ),
            make_link(
                request,
                path=self.format_path(request, "/"),
                rel="self",
                title="Landing page",
            ),

        ]

        links.extend(
            make_link(
                request,
                path=self.format_path(request, "/processes", service=service.service),
                rel="http://www.opengis.net/def/rel/ogc/1.0/processes",
                title=service.title,
            ) for service in self._executor.services
        )

        return web.Response(
            content_type="application/json",
            text=LandingPageModel(
                links=links,
            ).model_dump_json(),
        )
