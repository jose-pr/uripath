"""Built-in URI schemes, one submodule each.

A scheme class registers itself with `UriPath` when its submodule is
imported, and `UriPath` imports the submodule on demand the first time its
scheme is used. The class re-exports below (`HttpPath`, `FtpPath`, ...) are
resolved lazily (PEP 562): importing this package, or one scheme submodule
such as `.file`, imports no other backend, so a `file:` path never pays for
`http.client`.
"""

from __future__ import annotations

import importlib as _importlib
import typing as _ty

if _ty.TYPE_CHECKING:
    from .archive import TarUri as TarUri
    from .archive import ZipUri as ZipUri
    from .data import DataUri as DataUri
    from .dav import DavPath as DavPath
    from .file import FileUri as FileUri
    from .ftp import FtpPath as FtpPath
    from .git import GitPath as GitPath
    from .github import GitHubPath as GitHubPath
    from .gitlab import GitLabPath as GitLabPath
    from .http import HttpPath as HttpPath

#: Re-exported class name -> the submodule that defines it.
_EXPORTS = {
    "TarUri": "archive",
    "ZipUri": "archive",
    "DataUri": "data",
    "FileUri": "file",
    "FtpPath": "ftp",
    "HttpPath": "http",
    "DavPath": "dav",
    "GitHubPath": "github",
    "GitLabPath": "gitlab",
    "GitPath": "git",
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
