"""`Source` (the scheme, userinfo, host and port of a URI) and the helpers that
read and compose the text of one."""

from __future__ import annotations

from ._compose import SAFE_PATH, compose_host, compose_uri, percent_encode
from ._parse import ERRORS, fold_host, is_drive
from ._source import Source, same_authority

__all__ = [
    "ERRORS",
    "SAFE_PATH",
    "Source",
    "compose_host",
    "compose_uri",
    "fold_host",
    "is_drive",
    "percent_encode",
    "same_authority",
]
