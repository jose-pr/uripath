"""The path of a scheme that no class registered.

It builds, joins, compares and prints like any other; the first operation that
needs a server raises an `ImportError` that suggests names to look for.
"""

from __future__ import annotations

from ._path import URIPath

GROUP = "uripath.schemes"


def suggestions(scheme: str) -> str:
    """Where a class for `scheme` could come from: the entry-point group it
    registers in and three names to look for. They are patterns, not known
    packages. The name is the part of the scheme before its first `+`."""
    name = scheme.lower().split("+", 1)[0]
    return (
        f"a distribution that provides it registers a class in the entry-point "
        f"group {GROUP!r}. Names to look for, not known packages: "
        f'pip install "{name}path[uri]", uripath-{name}, {name}uripath'
    )


def no_class(scheme: str) -> ImportError:
    """The `ImportError` of an operation on a path whose scheme has no class."""
    return ImportError(
        f"no class is registered for the URI scheme {scheme.lower()!r}; "
        + suggestions(scheme)
    )


def _unavailable(name: str):
    """A primitive of `URIPath` that does the one thing a path of a scheme
    without a class can do about I/O."""

    def hook(self, *args, **kwargs):
        scheme = self.source.scheme
        if not scheme:
            # A relative path derived from one has no scheme to name.
            raise NotImplementedError(f"Method not implemented: {name}")
        raise no_class(scheme)

    hook.__name__ = name
    return hook


class UnregisteredURIPath(URIPath):
    """The class of a path whose scheme no class registered. It registers no
    scheme: a class registered later is found first. Every primitive of
    `URIPath` raises the `ImportError` of `no_class()`, so each operation
    derived from one does too."""

    __slots__ = ()
    #: The keyword arguments of the real class are that class's to name.
    _OPTIONS = None


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
    setattr(UnregisteredURIPath, _name, _unavailable(_name))
del _name
