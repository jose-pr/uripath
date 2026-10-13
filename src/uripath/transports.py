"""HTTP transports: the ones that exist, and what a new one starts from.

A transport is an object with `send()` and `close()` (`uripath.schemes.HTTPTransport`
is the built-in one). Another distribution provides one by declaring an entry
point in the `uripath.http_transports` group; `names()` lists them without
importing any and `get()` loads one. `prepare_request()` makes the checks the
contract asks of every transport before it sends.
"""

from __future__ import annotations

import typing as _ty

from .schemes import _elsewhere
from .schemes._http._body import prepare_body as _prepare_body
from .schemes._http._headers import (
    check_body as _check_body,
    check_headers as _check_headers,
    check_method as _check_method,
    check_timeout as _check_timeout,
    check_url as _check_url,
    has_header as _has_header,
    wants_decoding as _wants_decoding,
)

__all__ = ["GROUP", "PreparedRequest", "get", "names", "prepare_request"]

GROUP = "uripath.http_transports"
"""The entry-point group of the HTTP transports. An entry's name is the
transport's name (`requests`) and its value names a class that is built with
no arguments."""

_BUILTIN = "builtin"

# The methods whose request says `Content-Length: 0` when it has no body.
_EXPECTING_BODY = frozenset({"PATCH", "POST", "PUT"})


def _declared() -> "dict[str, _ty.Any]":
    """The entry points of `GROUP` by name, the first declaration of a name
    winning."""
    import importlib.metadata as _metadata

    try:
        found = _metadata.entry_points(group=GROUP)
    except TypeError:  # Python 3.9
        found = _metadata.entry_points().get(GROUP, ())
    declared: "dict[str, _ty.Any]" = {}
    for entry in found:
        declared.setdefault(entry.name, entry)
    return declared


def names() -> "tuple[str, ...]":
    """The names of the HTTP transports, sorted: `builtin`, every entry of
    `GROUP`, and the transports that another distribution provides whether or
    not it is installed. Nothing is imported."""
    return tuple(sorted({_BUILTIN, *_declared(), *_elsewhere.TRANSPORTS}))


def get(name: str) -> type:
    """The class of the transport called `name` (case-sensitive), loading its
    entry point. `builtin` is always `uripath.schemes.HTTPTransport`: no entry
    point replaces it.

    Raises `ImportError` naming what to install for a transport that another
    distribution provides and that is not installed, and `ValueError` naming
    the choices for any other name."""
    if name == _BUILTIN:
        from .schemes._http._builtin import HTTPTransport

        return HTTPTransport
    entry = _declared().get(name) if isinstance(name, str) else None
    if entry is not None:
        found = entry.load()
        if not callable(found):
            raise TypeError(f"the HTTP transport {name!r} is not a class")
        return found
    if isinstance(name, str) and name in _elsewhere.TRANSPORTS:
        raise _elsewhere.transport_not_installed(name)
    raise ValueError(
        f"{name!r} is not an HTTP transport "
        f"(expected one of {', '.join(map(repr, names()))})"
    )


class PreparedRequest(_ty.NamedTuple):
    """A request that passed the checks of the transport contract.

    `headers` hold text values, with the `Content-Length` of a body whose
    length is known (`0` for a `PATCH`, `POST` or `PUT` without a body) and an
    `Accept-Encoding` of `gzip, deflate` unless the caller named one. `body` is `None`, `bytes`, an object that sends exactly
    the `Content-Length` bytes when it is read or iterated, or an iterable of
    `bytes` to send chunked. `timeout` is `(connect, read)`. `decode` says
    whether the response decodes a `gzip` or `deflate` body: build it with
    `HTTPResponse(..., decode=decode)`."""

    method: str
    url: str
    headers: "dict[str, str]"
    body: _ty.Any
    timeout: "tuple[float | None, float | None]"
    decode: bool


def prepare_request(
    method: str,
    url: str,
    *,
    headers: "_ty.Mapping[str, str] | None",
    body: "bytes | _ty.BinaryIO | _ty.Iterable[bytes] | None" = None,
    timeout: "float | tuple | None",
) -> PreparedRequest:
    """The arguments of `send()` as the contract reads them.

    `method` is upper-cased. Raises `ValueError`, before anything is sent, for
    a method or header name that is not an HTTP token, a header value or URL
    with a control character, a URL with credentials or another scheme, a
    `Content-Length` that is not a count of bytes or exceeds the body, and a
    `timeout` that is not a positive number, `None` or a pair of them;
    `TypeError` for a `str` body. None of the messages quotes the URL or a
    header value. The fragment is dropped from `url`."""
    method = _check_method(method)
    _check_url(url)
    _check_body(body)
    timeout = _check_timeout(timeout)
    pairs = _check_headers(headers)
    sent = dict(pairs)
    body, length = _prepare_body(body, pairs)
    if length is not None:
        sent["Content-Length"] = str(length)
    elif not _has_header(sent, "Content-Length"):
        if isinstance(body, (bytes, bytearray, memoryview)):
            sent["Content-Length"] = str(memoryview(body).nbytes)
        elif body is None and method in _EXPECTING_BODY:
            sent["Content-Length"] = "0"
    decode = _wants_decoding(sent.items())
    if not _has_header(sent, "Accept-Encoding"):
        sent["Accept-Encoding"] = "gzip, deflate"
    return PreparedRequest(method, url.split("#", 1)[0], sent, body, timeout, decode)
