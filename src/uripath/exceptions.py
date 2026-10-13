"""The exceptions and the warning of uripath.

`URIPathError` is the base of what goes wrong at run time. A caller's bad
argument is a plain `ValueError` or `TypeError`, and a failed read or write
is the `OSError` of the kind `pathlib` raises.
"""

from __future__ import annotations

__all__ = [
    "InsecureTransportWarning",
    "URIPathError",
    "URISyntaxError",
    "UnsupportedSchemeError",
]


class URIPathError(Exception):
    """The base of the errors uripath raises."""


class URISyntaxError(URIPathError, ValueError):
    """Text that is not a URI, or not the part of one that was asked for: a port
    that is not 0-65535, a malformed host, a `zip:` URI without the scheme of
    its archive. The message names what is wrong and never the text, which can
    carry a password."""


class UnsupportedSchemeError(URIPathError, ValueError):
    """A scheme that no class registered. The message lists the registered
    ones."""


class InsecureTransportWarning(UserWarning):
    """A `RepoBackend` is about to send an `Authorization` header (its token,
    or one given in `headers=`) over plain `http://` to a host that is not
    this machine, where anyone on the route can read it."""
