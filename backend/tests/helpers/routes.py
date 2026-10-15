"""Enumerate the API routes of an app, whatever FastAPI's internal nesting looks like.

Older FastAPI keeps ``APIRoute`` objects in ``app.routes``. Newer versions wrap included
routers lazily and expose the flattened routes through ``effective_route_contexts()``. Both
shapes offer ``path``, ``methods`` and ``dependant``, which is all the tests rely on.
Callers must assert that the result is non-empty, so an enumeration that silently breaks
cannot make a test pass vacuously.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

IGNORED_METHODS = {"HEAD", "OPTIONS"}


@dataclass(frozen=True)
class ApiRoute:
    path: str
    methods: frozenset[str]
    dependant: Dependant | None


def _flatten(routes: list[Any]) -> Iterator[Any]:
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        else:
            yield route


def iter_api_routes(app: FastAPI) -> Iterator[ApiRoute]:
    for route in _flatten(list(app.routes)):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or not path.startswith("/api/"):
            continue
        yield ApiRoute(
            path=path,
            methods=frozenset(methods) - IGNORED_METHODS,
            dependant=getattr(route, "dependant", None),
        )


def dependency_names(dependant: Dependant | None) -> set[str]:
    """Qualified names of every dependency callable reachable from ``dependant``."""
    names: set[str] = set()
    if dependant is None:
        return names
    for sub in dependant.dependencies:
        if sub.call is not None:
            names.add(sub.call.__qualname__)
        names |= dependency_names(sub)
    return names
