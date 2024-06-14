#
# Build swagger documentation
#
import json
import sys  # noqa

from inspect import isclass

from aiohttp import web
from aiohttp.hdrs import METH_ALL, METH_ANY
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    Json,
    JsonValue,
    TypeAdapter,
)
from typing_extensions import Dict, List, Literal, Optional, Tuple, Type

ModelAlias = Type[BaseModel] | TypeAdapter

_models: List[Tuple[str, ModelAlias]] = []

oapi_title = "Py-Qgis services admin"
oapi_description = "Manage Py-Qgis services clusters"
oapi_version = "3.0.0"


class SwaggerError(Exception):
    pass


class Tag(BaseModel):
    description: str
    name: str


class Info(BaseModel):
    title: str
    description: str
    version: str


# Conveys an identifier for the link's context.
# See https://www.iana.org/assignments/link-relations/link-relations.xhtml
LinkRel = Literal[
    "self",
    "first",
    "last",
    "next",
    "prev",
    "related",
    "up",
]


class Link(BaseModel):
    # Supplies the URI to a remote resource (or resource fragment).
    href: AnyHttpUrl
    # The type or semantics of the relation.
    rel: str
    # Mime type of the data returne by the link
    mime_type: Optional[str] = Field(default=None, serialization_alias="type")
    # human-readable identifier for the link
    title: str = ""
    # A long description for the link
    description: Optional[str] = None
    # Estimated size (in bytes) of the online resource response
    length: Optional[int] = None
    # Is the link templated with '{?<keyword>}'
    templated: bool = False
    # Language of the resource referenced
    hreflang: Optional[str] = None


class OpenApiDocument(BaseModel):
    """ Swagger/OpenApi document
    """
    openapi: str = oapi_version
    paths: Dict[str, Json]
    definitions: Dict[str, Json]
    tags: List[Tag]
    info: Info


def model(model: ModelAlias, name: Optional[str] = None) -> ModelAlias:
    """ Collect models
    """
    if isinstance(model, TypeAdapter):
        if not name:
            raise ValueError(f"Missing 'name' for {type(model)}")
    else:
        name = model.__name__
    _models.append((name, model))
    return model


def schemas(ref_template: str = "#/definitions/{model}") -> Dict[str, JsonValue]:  # noqa: RUF027
    """ Build schema definitions dictionnary from models
    """
    schema_definitions = {}
    for name, model in _models:
        # print(model, file=sys.stderr)
        match model:
            case TypeAdapter():
                schema = model.json_schema(ref_template=ref_template)
            case _:
                schema = model.model_json_schema(ref_template=ref_template)
        # Extract subdefinitions
        defs = schema.pop('$defs', {})
        for n, d in defs.items():
            schema_definitions[n] = d

        schema_definitions[name] = schema

    return schema_definitions


def _get_method_names_for_handler(route):
    # Return all valid method names in handler if the method is *,
    # otherwise return the specific method.
    if route.method == METH_ANY:
        return {
            attr for attr in dir(route.handler)
            if attr.upper() in METH_ALL
        }
    else:
        return {
            attr for attr in dir(route.handler)
            if attr.upper() in METH_ALL and attr.upper() == route.method
        }


def paths(app: web.Application) -> Dict:
    """ Extract swagger doc from aiohttp routes handlers
    """
    import yaml

    paths: Dict[str, Dict[str, str]] = {}
    for route in app.router.routes():

        methods = {}
        try:
            if route._resource is None:
                continue

            url_info = route._resource.get_info()
            if url_info.get("path", None):
                url = url_info.get("path")
            else:
                url = url_info.get("formatter")

            if not url:
                # not url ?
                continue

            if isclass(route.handler) and issubclass(route.handler, web.View):
                for method_name in _get_method_names_for_handler(route):
                    method = getattr(route.handler, method_name)
                    if method.__doc__ is not None:
                        methods[method_name] = yaml.full_load(method.__doc__)
            else:
                try:
                    if route.handler.__doc__:
                        methods[route.method.lower()] = yaml.full_load(route.handler.__doc__)
                except AttributeError:
                    continue
        except (yaml.scanner.ScannerError, yaml.parser.ParserError) as err:
            raise SwaggerError(
                f"Yaml error for {route.handler.__qualname__}: {err}",
            ) from None

        paths.setdefault(url, {}).update(methods)
        # paths[url] = methods
    return paths


def doc(app: web.Application, tags: List[Tag], api_version: str) -> OpenApiDocument:
    return OpenApiDocument(
        paths={k: json.dumps(v) for k, v in paths(app).items()},
        definitions={k: json.dumps(v) for k, v in schemas().items()},
        tags=tags,
        info=Info(
            description=oapi_description,
            title=oapi_title,
            version=api_version,
        ),
    )
