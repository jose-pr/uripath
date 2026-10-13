"""pathlib-style paths for URIs."""

from __future__ import annotations

from ._pathtext import as_path
from ._transfer import copy_stream
from ._uri import URI, URILike
from ._version import __version__
from .exceptions import URIPathError, URISyntaxError, UnsupportedSchemeError
from .query import Query, QueryLike
from .schemes import URIPath
from .source import Source

__all__ = [
    "__version__",
    "as_path",
    "copy_stream",
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
