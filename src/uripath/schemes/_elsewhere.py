"""Schemes and an HTTP transport that other distributions provide.

`uripath` knows their names. A path of one of these schemes builds, joins,
compares and prints like any other, and the first operation that needs the
server raises an `ImportError` that names what to install.
"""

from __future__ import annotations

from . import URIPath

#: Scheme -> (the distribution that provides it, its import name, what to run
#: to get it). A name listed here is known without the distribution: a path of
#: it is built, and its I/O raises an `ImportError` naming what to install. An
#: installed distribution registers its own class (an entry point of
#: `uripath.schemes`), which is found first.
SCHEMES = {
    "sftp": (
        "uripath-sftp",
        "uripath_sftp",
        'pip install "uripath-sftp[paramiko]" (or "uripath-sftp[asyncssh]")',
    ),
    "s3": (
        "uripath-objstore",
        "uripath_objstore",
        'pip install "uripath-objstore[s3]"',
    ),
    "gs": (
        "uripath-objstore",
        "uripath_objstore",
        'pip install "uripath-objstore[gs]"',
    ),
    "az": (
        "uripath-objstore",
        "uripath_objstore",
        'pip install "uripath-objstore[az]"',
    ),
}

#: The HTTP transport `URIPATH_HTTP_TRANSPORT=requests` and `with_session()`
#: ask for: (distribution, import name, what to run).
REQUESTS_TRANSPORT = (
    "uripath-http-requests",
    "uripath_http_requests",
    "pip install uripath-http-requests",
)


def not_installed(scheme: str) -> ImportError:
    """The `ImportError` for a scheme another distribution provides."""
    distribution, package, install = SCHEMES[scheme]
    return ImportError(
        f"the {scheme!r} scheme is provided by the {distribution} distribution: "
        f"{install}",
        name=package,
    )


def requests_transport_missing() -> ImportError:
    """The `ImportError` for the `requests` HTTP transport."""
    distribution, package, install = REQUESTS_TRANSPORT
    return ImportError(
        f"the 'requests' HTTP transport is provided by the {distribution} "
        f"distribution: {install}",
        name=package,
    )


def _unavailable(name: str):
    """A hook of `URIPath` that does the one thing a path of a missing scheme
    can do about I/O."""

    def hook(self, *args, **kwargs):
        raise not_installed(self.source.scheme.lower())

    hook.__name__ = name
    return hook


class ProvidedElsewhere(URIPath):
    """The class of a path whose scheme another distribution provides and that is
    not installed. It registers no scheme: an installed distribution registers
    its own class, which is found first. Every primitive of `URIPath` raises
    the `ImportError` of `not_installed()`, so each operation derived from one
    does too."""

    __slots__ = ()

    def _initbackend(self):
        raise not_installed(self.source.scheme.lower())


for _name in (
    "stat",
    "_open",
    "_listdir",
    "_scandir",
    "unlink",
    "_mkdir",
    "rmdir",
    "rename",
    "chmod",
    "_chown",
    "_utime",
    "readlink",
    "_symlink_to",
):
    setattr(ProvidedElsewhere, _name, _unavailable(_name))
del _name
