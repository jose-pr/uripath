"""The RFC 3986 pieces uripath needs, on the standard library: the split of a
URI reference into its five components, and percent-decoding and -encoding."""

from __future__ import annotations

import re as _re
import typing as _ty
from urllib.parse import quote_from_bytes as _quote_from_bytes
from urllib.parse import unquote_to_bytes as _unquote_to_bytes

__all__ = ["Split", "decode", "encode", "split"]


class Split(_ty.NamedTuple):
    """The components of a URI reference as written: `None` for one that is
    absent, `""` for one that is present and empty (`http://h/x?` has the query
    `""`, `http://h/x` has none), the path always a `str`."""

    scheme: "str | None"
    authority: "str | None"
    path: str
    query: "str | None"
    fragment: "str | None"


# RFC 3986 appendix B. Like the reference expression, `.` does not match a
# newline, so a fragment ends at one and what follows is dropped.
_SPLIT = _re.compile(
    r"(?:([A-Za-z][A-Za-z0-9+.-]*):)?"  # scheme (3.1)
    r"(?://([^/?#]*))?"  # authority (3.2)
    r"([^?#]*)"  # path (3.3)
    r"(?:\?([^#]*))?"  # query (3.4)
    r"(?:#(.*))?"  # fragment (3.5)
)


def split(text: str) -> Split:
    """The five components of `text`. Any text splits: nothing is validated."""
    return Split(*_SPLIT.match(text).groups())


def decode(text: str, errors: str = "strict", encoding: str = "utf-8") -> str:
    """`text` with each `%XX` escape replaced by its byte, the bytes read as
    `encoding`.

    Text that is not an escape stays as it is: a `%` that is not followed by two
    hexadecimal digits (in either case) is a `%`, and non-ASCII characters are
    kept. Bytes that are not valid in `encoding` are handled by `errors`, and
    `surrogateescape` carries each through the result."""
    if encoding == "utf-8" and "%" not in text and text.isascii():
        return text
    return _unquote_to_bytes(text.encode(encoding, errors)).decode(encoding, errors)


def encode(
    data: "str | bytes",
    safe: str = "",
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> str:
    """`data` percent-encoded: every byte that is not unreserved (RFC 3986 2.3)
    or in `safe` becomes `%XX` with upper-case digits. A `str` is first encoded
    as `encoding` with `errors`; `bytes` are used as they are. `safe` is ASCII."""
    if not isinstance(data, bytes):
        data = data.encode(encoding, errors)
    return _quote_from_bytes(data, safe)
