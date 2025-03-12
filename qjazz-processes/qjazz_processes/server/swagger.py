
from inspect import isclass
from typing import (
    Optional,
    Sequence,
)

from aiohttp import web
from aiohttp.hdrs import METH_ALL, METH_ANY
from pydantic import (
    Field,
    Json,
    JsonValue,
    TypeAdapter,
)

from qjazz_contrib.core.config import ConfigBase, section

from ..schemas import JsonModel

OAPI_VERSION = "3.0.0"


JsonAdapter: TypeAdapter = TypeAdapter(JsonValue)


def dump_json(v: JsonValue) -> str:
    return JsonAdapter.dump_json(v).decode()


@section("oapi")
class OapiConfig(ConfigBase):
    """ OAPI configuration
    """
    title: str = Field("Py-Qgis-Processes")
    description: str = Field(
        "Publish Qgis processing algorithms as OGC api processes",
    )


#
# Model factory (use as decorator)
#
ModelAlias = type[JsonModel] | TypeAdapter

_models: list[tuple[str, ModelAlias]] = []


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


#
# OpenApi Document
#

class Tag(JsonModel):
    description: str
    name: str


class Info(JsonModel):
    title: str
    description: str
    version: str


class OpenApiDocument(JsonModel):
    openapi: str = OAPI_VERSION
    paths: dict[str, Json]
    definitions: dict[str, Json]
    tags: Sequence[Tag]
    info: Info


def doc(app: web.Application, tags: list[Tag], api_version: str, conf: OapiConfig) -> OpenApiDocument:
    return OpenApiDocument(
        paths={k: dump_json(v) for k, v in paths(app).items()},
        definitions={k: dump_json(v) for k, v in schemas().items()},
        tags=tags,
        info=Info(
            description=conf.description,
            title=conf.title,
            version=api_version,
        ),
    )


class SwaggerError(Exception):
    pass


def schemas(ref_template: str = "#/definitions/{model}") -> dict[str, JsonValue]:  # noqa RUF027
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


def paths(app: web.Application) -> dict:
    """ Extract swagger doc from aiohttp routes handlers
    """
    import ruamel.yaml

    yaml = ruamel.yaml.YAML()

    paths: dict[str, dict[str, str]] = {}
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
                # no url ?
                continue

            if isclass(route.handler) and issubclass(route.handler, web.View):
                for method_name in _get_method_names_for_handler(route):
                    method = getattr(route.handler, method_name)
                    if method.__doc__:
                        methods[method_name] = yaml.load(method.__doc__)
            else:
                try:
                    if route.handler.__doc__:
                        methods[route.method.lower()] = yaml.load(route.handler.__doc__)
                except AttributeError:
                    continue
        except (ruamel.yaml.scanner.ScannerError, ruamel.yaml.parser.ParserError) as err:
            raise SwaggerError(
                f"Yaml error for {route.handler.__qualname__}: {err}",
            ) from None

        if methods:
            paths.setdefault(url, {}).update(methods)
    return paths


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
