
from urllib.parse import urlencode

from aiohttp import web
from pydantic import Field, TypeAdapter, ValidationError
from typing_extensions import (
    Annotated,
    Sequence,
    cast,
)

from .protos import (
    ErrorResponse,
    HandlerProto,
    JobResultsAdapter,
    JobStatus,
    JsonDict,
    Link,
    href,
    job_realm,
    make_link,
    swagger,
)


@swagger.model
class JobList(swagger.JsonModel):
    jobs: Sequence[JobStatus]
    links: Sequence[Link]


LimitParam: TypeAdapter[int] = TypeAdapter(Annotated[int, Field(ge=1, lt=1000)])
PageParam: TypeAdapter[int] = TypeAdapter(Annotated[int, Field(ge=0)])


class Jobs(HandlerProto):

    async def job_status(self, request: web.Request) -> web.Response:
        """
        summary: Get Job status
        description: |
            Returns the job status
        parameters:
            - in: path
              name: JobId
              schema:
                type: string
              required: true
              description: Job id
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobStatus'
            "404":
                description: Job not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        job_id = request.match_info['JobId']

        job_status = await self._executor.job_status(job_id, realm=job_realm(request))
        if not job_status:
            return ErrorResponse.response(404, message=job_id)

        location = self.format_path(request, f"/jobs/{job_id}")
        job_status.links.append(
            make_link(request, path=location, rel="self", title="Job status"),
        )

        if job_status.status == job_status.SUCCESS:
            location = self.format_path(request, f"/jobs/{job_id}/results")
            job_status.links.append(
                make_link(
                    request,
                    path=location,
                    rel="http://www.opengis.net/def/rel/ogc/1.0/results",
                    title="Job results",
                ),
            )

        return web.Response(
            headers={'Location': href(request, location)},
            content_type="application/json",
            text=job_status.model_dump_json(),
        )

    async def list_jobs(self, request: web.Request) -> web.Response:
        """
        summary: Get Job list
        description: |
            Returns the list job's status
        parameters:
            - in: query
              name: limit
              schema:
                 type: integer
                 minimum: 1
                 maximum: 1000
                 default: 10
              required: false
              description: Number of element returned
            - in: query
              name: page
              schema:
                 type: integer
                 minimum: 0
                 default: 0
              required: false
              description: Start page index
            - in: query
              name: status
              required: false
              schema:
                type: arary
                items:
                  type: string
            - in: query
              name: processID
              required: false
              schema:
                type: array
                items:
                   type: string
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job status list
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobList
            "404":
                description: Jobs not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse
        """
        # Allow passing service as query parameter
        service = request.query.get('service')

        try:
            limit = LimitParam.validate_python(request.query.get('limit', 10))
            page = PageParam.validate_python(request.query.get('page', 0))
        except ValidationError as err:
            details = err.errors(include_context=False, include_url=False)
            ErrorResponse.raises(
                web.HTTPBadRequest,
                message="Invalid parameter",
                details=cast(JsonDict, details),
            )

        # Filters
        process_ids = request.query.getall('processID', ())
        filtered_status = request.query.getall('status', ())

        realm = job_realm(request)

        async def filtered_jobs():
            async for st in self._executor.iter_jobs(
                service,
                realm=realm,
                cursor=page,
                limit=limit,
            ):
                if process_ids and not st.process_id not in process_ids:
                    continue
                if filtered_status and st.status not in filtered_status:
                    continue

                yield st

        jobs = [st async for st in filtered_jobs()]

        params = {
            'processID': process_ids,
            'status': filtered_status,
            'limit': limit,
            'page': page or (),
        }

        links = [
            make_link(
                request,
                path=self.format_path(request, "/jobs/", query=urlencode(params, doseq=True)),
                rel="self",
                title="Job list",
            ),
        ]

        if len(jobs) >= limit:
            params.update(page=page + 1)
            links.append(
                make_link(
                    request,
                    path=self.format_path(request, "/jobs/", query=urlencode(params, doseq=True)),
                    rel="next",
                    title="Job list",
                ),
            )

        if page > 0:
            params.update(page=page - 1)
            links.append(
                make_link(
                    request,
                    path=self.format_path(request, "/jobs/", query=urlencode(params, doseq=True)),
                    rel="prev",
                    title="Job list",
                ),
            )

        return web.Response(
            content_type="application/json",
            text=JobList(jobs=jobs, links=links).model_dump_json(),
        )

    async def job_results(self, request: web.Request) -> web.Response:
        """
        summary: retrieve the result(s) of a job
        description: |
            List available results
        parameters:
            - in: path
              name: JobId
              schema:
                type: string
              required: true
              description: Job id
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobResults'
            "404":
                description: Job not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        job_id = request.match_info['JobId']

        results = await self._executor.job_results(job_id, realm=job_realm(request))
        if not results:
            return ErrorResponse.response(404, "No results", details={'jobId': job_id})
        return web.Response(
            content_type="application/json",
            body=JobResultsAdapter.dump_json(results, by_alias=True, exclude_none=True),
        )

    async def dismiss_job(self, request: web.Request) -> web.Response:
        """
        summary: cancel a job execution, remove a finished job
        description: |
            Cancel a job execution and remove it from the jobs list.
        parameters:
            - in: path
              name: JobId
              schema:
                type: string
              required: true
              description: Job id
        tags:
          - jobs
        responses:
            "200":
                description: >
                    Job status
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/JobStatus'
            "404":
                description: Job not found
                content:
                    application/json:
                        schema:
                            $ref: '#/definitions/ErrorResponse'
        """
        job_id = request.match_info['JobId']

        st = await self._executor.dismiss(job_id, realm=job_realm(request))
        if not st:
            return ErrorResponse.response(404, "Job not found", details={'jobId': job_id})

        return web.Response(
            content_type="application/json",
            text=st.model_dump_json(),
        )
