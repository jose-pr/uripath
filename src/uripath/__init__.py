"""pathlib-style paths for URIs."""

from __future__ import annotations

from ._uri import URI, URILike
from .exceptions import URIPathError, URISyntaxError, UnsupportedSchemeError
from .query import Query, QueryLike
from .schemes import URIPath
from .source import Source

__all__ = [
    "Query",
    "QueryLike",
    "Source",
    "URI",
    "URILike",
    "URIPath",
    "URIPathError",
    "URISyntaxError",
    "UnsupportedSchemeError",
]
