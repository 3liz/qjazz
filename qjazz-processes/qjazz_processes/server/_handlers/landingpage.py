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
class LandingPageModel(swagger.JsonModel):
    links: Sequence[Link]


class LandingPage(HandlerProto):

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
        return web.Response(
            content_type="application/json",
            text=LandingPageModel(
                links=[
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
                        path=self.format_path(request, "/"),
                        rel="self",
                        title="Landing page",
                    ),
                ],
            ).model_dump_json(),
        )
