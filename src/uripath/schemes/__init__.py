"""Built-in URI schemes, one submodule each.

A scheme class registers itself with `URIPath` when its submodule is
imported, and `URIPath` imports the submodule on demand the first time its
scheme is used. The class re-exports below (`HTTPURIPath`, `FTPURIPath`, ...) are
resolved lazily (PEP 562): importing this package, or one scheme submodule
such as `.file`, imports no other backend, so a `file:` path never pays for
`http.client`.
"""

from __future__ import annotations

import importlib as _importlib
import typing as _ty

if _ty.TYPE_CHECKING:
    from .archive import TarURIPath as TarURIPath
    from .archive import ZipURIPath as ZipURIPath
    from .data import DataURIPath as DataURIPath
    from .dav import DAVURIPath as DAVURIPath
    from .file import FileURIPath as FileURIPath
    from .ftp import FTPURIPath as FTPURIPath
    from .git import GitURIPath as GitURIPath
    from .github import GitHubURIPath as GitHubURIPath
    from .gitlab import GitLabURIPath as GitLabURIPath
    from .http import HTTPURIPath as HTTPURIPath

#: Re-exported class name -> the submodule that defines it.
_EXPORTS = {
    "TarURIPath": "archive",
    "ZipURIPath": "archive",
    "DataURIPath": "data",
    "FileURIPath": "file",
    "FTPURIPath": "ftp",
    "HTTPURIPath": "http",
    "DAVURIPath": "dav",
    "GitHubURIPath": "github",
    "GitLabURIPath": "gitlab",
    "GitURIPath": "git",
}


def __getattr__(name: str):
    submodule = _EXPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        module = _importlib.import_module(f"{__name__}.{submodule}")
    except ImportError as error:
        # Only ImportError: a dependency that fails at import for any other
        # reason is a real defect and must stay visible.
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
            f" (its optional dependency is not importable: {error})"
        ) from error
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
