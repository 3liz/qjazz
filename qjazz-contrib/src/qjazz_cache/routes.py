"""Dict like object for handling templated routing

The code for Dynamic route handling has been borrowed
from aiohttp https://github.com/aio-libs/aiohttp licensed under
Apache License, Version 2.0  (http://www.apache.org/licenses/LICENSE-2.0)

Copyright aio-libs contributors.
"""

import re

from pathlib import PurePosixPath
from typing import (
    Final,
    Iterable,
    Iterator,
    Optional,
    Pattern,
    Protocol,
)
from urllib.parse import SplitResult, urlsplit

from qjazz_core.condition import assert_postcondition

Url = SplitResult

ROUTE_RE: Final[Pattern[str]] = re.compile(r"(\{[_a-zA-Z][^{}]*(?:\{[^{}]*\}[^{}]*)*\})")
PATH_SEP: Final[str] = re.escape("/")


class RouteDef(Protocol):
    @property
    def is_dynamic(self) -> bool: ...

    @property
    def cannonical(self) -> tuple[str, Url]: ...

    def relative_to(self, location: str) -> Optional[tuple[str, Url]]: ...

    def resolve_path(self, path: PurePosixPath) -> Optional[tuple[str, Url]]: ...


class Routes:
    def __init__(self, search_paths: dict[str, str]):
        def build_routes() -> Iterator[tuple[str, RouteDef]]:
            for location, url in search_paths.items():
                if not location.startswith("/"):
                    raise ValueError("Search path route must start with '/'")
                if not ("{" in location or "}" in location or ROUTE_RE.search(location)):
                    yield location, StaticRoute(location, url)
                else:
                    yield location, DynamicRoute(location, url)

        self._routes: dict[str, RouteDef] = dict(build_routes())

    @property
    def cannonical(self) -> Iterator[tuple[str, Url]]:
        return (route.cannonical for route in self._routes.values())

    @property
    def routes(self) -> Iterable[RouteDef]:
        return self._routes.values()

    def locations(self, location: Optional[str] = None) -> Iterable[tuple[str, Url]]:
        """List compatible search paths

        Arguments:
        location -- A location prefix
        """
        urls: Iterable[tuple[str, Url]]
        if location:
            route = self._routes.get(location)
            match route:
                case StaticRoute():
                    urls = ((location, route._url),)
                case DynamicRoute():
                    # The location matched a dynamic url template
                    # which is not a valid input route
                    urls = ()
                case _:
                    # Exact match route is not found check for compatible locations
                    # i.e: all routes that is *relative* to the given location.
                    urls = filter(
                        None,
                        (route.relative_to(location) for route in self._routes.values()),
                    )
        else:
            # Returns only static routes
            urls = (
                (str(route._location), route._url) for route in self._routes.values() if isinstance(route, StaticRoute)
            )

        return urls


def validate_url(urlstr: str) -> Url:
    url = urlsplit(urlstr)
    if not url.scheme:
        url = url._replace(scheme="file")
    return url


class StaticRoute(RouteDef):
    is_dynamic: Final[bool] = False

    def __init__(self, location: str, url: str):
        self._location = PurePosixPath(location)
        self._url = validate_url(url)

    @property
    def cannonical(self) -> tuple[str, Url]:
        return (str(self._location), self._url)

    def relative_to(self, location: str) -> Optional[tuple[str, Url]]:
        if self._location.is_relative_to(location):
            return (str(self._location), self._url)
        else:
            return None

    def resolve_path(self, path: PurePosixPath) -> Optional[tuple[str, Url]]:
        if path.is_relative_to(self._location):
            return (str(self._location), self._url)
        else:
            return None


class DynamicRoute(RouteDef):
    is_dynamic: Final[bool] = True

    DYN = re.compile(r"\{(?P<var>[_a-zA-Z][_a-zA-Z0-9]*)\}")
    DYN_WITH_RE = re.compile(r"\{(?P<var>[_a-zA-Z][_a-zA-Z0-9]*):(?P<re>.+)\}")
    GOOD = r"[^{}/]+"

    def __init__(self, location: str, url: str):
        self._location = location
        self._url = validate_url(url)

        # Build the dynamic pattern
        pattern = ""
        formatter = ""

        for part in ROUTE_RE.split(location):
            pmatch = self.DYN.fullmatch(part)
            if pmatch:
                pattern += "(?P<{}>{})".format(pmatch.group("var"), self.GOOD)
                formatter += "{" + pmatch.group("var") + "}"
                continue

            pmatch = self.DYN_WITH_RE.fullmatch(part)
            if pmatch:
                pattern += "(?P<{var}>{re})".format(**pmatch.groupdict())
                formatter += "{" + pmatch.group("var") + "}"
                continue

            if "{" in part or "}" in part:
                raise ValueError(f"Invalid path '{location}'['{part}']")

            formatter += part
            pattern += re.escape(part)

        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Bad pattern '{pattern}': {exc}") from None

        assert_postcondition(compiled.pattern.startswith(PATH_SEP))
        assert_postcondition(formatter.startswith("/"))
        self._pattern = compiled
        self._formatter = formatter

    @property
    def cannonical(self) -> tuple[str, Url]:
        return (self._location, self._url)

    def _match(self, location: str) -> Optional[dict[str, str]]:
        pmatch = self._pattern.match(location)
        if pmatch is None:
            return None
        else:
            return pmatch.groupdict()

    def relative_to(self, location: str) -> Optional[tuple[str, Url]]:
        # Location must match the url pattern
        args = self._match(location)
        if args:
            this_location = self._formatter.format_map(args)
            if PurePosixPath(this_location).is_relative_to(location):
                # Format the resulting url
                url = self._url.geturl().format_map(args)
                return (this_location, urlsplit(url))

        return None

    def resolve_path(self, path: PurePosixPath) -> Optional[tuple[str, Url]]:
        args = self._match(str(path))
        if args:
            location = self._formatter.format_map(args)
            if path.is_relative_to(location):
                url = self._url.geturl().format_map(args)
                return (location, urlsplit(url))

        return None
