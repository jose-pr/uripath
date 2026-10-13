"""HTTP transports: the ones that exist, and what a new one starts from.

A transport is an object with `send()` and `close()` (`uripath.schemes.HTTPTransport`
is the built-in one). Another distribution provides one by declaring an entry
point in the `uripath.http_transports` group; `names()` lists them without
importing any and `get()` loads one.
"""

from __future__ import annotations

import typing as _ty

from .schemes import _elsewhere

__all__ = ["GROUP", "get", "names"]

GROUP = "uripath.http_transports"
"""The entry-point group of the HTTP transports. An entry's name is the
transport's name (`requests`) and its value names a class that is built with
no arguments."""

_BUILTIN = "builtin"


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
