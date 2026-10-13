"""Which class a scheme name belongs to: the classes that registered, the built-in table and the `uripath.schemes` entry points."""

from __future__ import annotations

import threading as _threading
import typing as _ty

if _ty.TYPE_CHECKING:
    from . import URIPath

#: `(entry_points function, {scheme: entry point})` for the
#: `uripath.schemes` group, read once per lookup function; a scheme no
#: plugin declares is a dictionary miss and adds nothing to it.
_ENTRY_POINTS: "tuple[object, dict[str, object]] | None" = None


#: Schemes whose entry point loaded without registering them: loading it
#: again cannot help.
_ENTRY_POINTS_LOADED: "set[str]" = set()


#: Built-in scheme -> the module that defines its class. A name listed here is
#: resolved from this table before any entry point is consulted.
_BUILTIN_SCHEMES = {
    "file": "uripath.schemes.file",
    "data": "uripath.schemes.data",
    "zip": "uripath.schemes.archive",
    "tar": "uripath.schemes.archive",
    "archive": "uripath.schemes.archive",
    "archive+zip": "uripath.schemes.archive",
    "archive+tar": "uripath.schemes.archive",
    "ftp": "uripath.schemes.ftp",
    "ftps": "uripath.schemes.ftp",
    "http": "uripath.schemes.http",
    "https": "uripath.schemes.http",
    "dav": "uripath.schemes.dav",
    "davs": "uripath.schemes.dav",
    "github": "uripath.schemes.github",
    "gitlab": "uripath.schemes.gitlab",
    "git": "uripath.schemes.git",
    "git+github": "uripath.schemes.git",
    "git+gitlab": "uripath.schemes.git",
}


#: Scheme -> the class that registered it, filled when the class is defined.
_CLAIMS: "dict[str, type[URIPath]]" = {}


#: Schemes a class took with `replace=True`; a built-in class defined after
#: one of them leaves it with the replacement.
_REPLACED: "set[str]" = set()


#: Makes checking a claim and recording it one step.
_CLAIMS_LOCK = _threading.Lock()


def _forget_entry_points() -> None:
    global _ENTRY_POINTS
    _ENTRY_POINTS = None
    _ENTRY_POINTS_LOADED.clear()


def _declared_entry_points() -> "dict[str, object]":
    """The `uripath.schemes` entry points by scheme name, the first
    declaration of a name winning. Scanning every distribution cost 13-29 ms
    per construction with an unregistered scheme (`C:/x` on Windows
    included), so the group is read once per lookup function and dropped when
    a `URIPath` subclass is defined (`_forget_entry_points`)."""
    global _ENTRY_POINTS
    import importlib.metadata as _metadata

    cached = _ENTRY_POINTS
    if cached is None or cached[0] is not _metadata.entry_points:
        try:
            eps = _metadata.entry_points(group="uripath.schemes")
        except TypeError:
            # Python 3.9 fallback
            eps = _metadata.entry_points().get("uripath.schemes", ())
        declared: "dict[str, object]" = {}
        for ep in eps:
            declared.setdefault(ep.name, ep)
        cached = _ENTRY_POINTS = (_metadata.entry_points, declared)
    return cached[1]


def _is_builtin_class(scheme: str, cls: type) -> bool:
    """Whether `cls` is defined in the module (or package) the built-in
    table names for `scheme`."""
    module = _BUILTIN_SCHEMES.get(scheme)
    return module is not None and (
        cls.__module__ == module or cls.__module__.startswith(module + ".")
    )


def _same_definition(a: type, b: type) -> bool:
    """Whether two classes come from one `class` statement run twice (a
    reload, a function body called again): same module, same qualified name."""
    return a.__module__ == b.__module__ and a.__qualname__ == b.__qualname__


def _claim_schemes(cls: type, replace: bool) -> None:
    """Register the schemes `cls` lists in its own `__SCHEMES`.

    A name a different class holds, or a built-in name whose class is not the
    built-in one, is a `ValueError` unless `replace` is true; the same
    definition run again takes its names over. Nothing is registered when any
    name is refused.
    """
    names = tuple(dict.fromkeys(cls.__dict__.get(f"_{cls.__name__}__SCHEMES", ())))
    with _CLAIMS_LOCK:
        taking = []
        for name in names:
            held = _CLAIMS.get(name)
            if replace:
                taking.append(name)
            elif held is None:
                if name in _BUILTIN_SCHEMES and not _is_builtin_class(name, cls):
                    raise ValueError(
                        f"{name!r} is a built-in URI scheme; pass replace=True "
                        f"in the class statement of {cls.__qualname__} to replace it"
                    )
                taking.append(name)
            elif _same_definition(held, cls):
                taking.append(name)
            elif name in _REPLACED and _is_builtin_class(name, cls):
                continue
            else:
                raise ValueError(
                    f"URI scheme {name!r} is already registered by "
                    f"{held.__module__}.{held.__qualname__}; pass replace=True "
                    f"in the class statement of {cls.__qualname__} to replace it"
                )
        for name in taking:
            _CLAIMS[name] = cls
            if replace:
                _REPLACED.add(name)
