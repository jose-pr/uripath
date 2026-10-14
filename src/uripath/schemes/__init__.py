"""The contract of a URI scheme, the registry of schemes and the built-in schemes.

`URIPath` is the class a scheme subclasses: defining a subclass that lists
`__SCHEMES` registers it. A built-in scheme is a private module that
`URIPath` imports the first time its scheme is used; the names below are
exported from here and resolved lazily (PEP 562), so importing this package,
or building a `file:` path, imports no other scheme and a `file:` path never
pays for the HTTP client.
"""

from __future__ import annotations

import importlib as _importlib
import sys as _sys
import types as _types
import typing as _ty

from ._delegate import DelegatingURIPath as DelegatingURIPath
from ._path import DerivedBackend
from ._path import URIPath as URIPath

if _ty.TYPE_CHECKING:
    from ._archive import ArchiveTarURIPath as ArchiveTarURIPath
    from ._archive import ArchiveURIPath as ArchiveURIPath
    from ._archive import ArchiveZipURIPath as ArchiveZipURIPath
    from ._archive import TarURIPath as TarURIPath
    from ._archive import ZipURIPath as ZipURIPath
    from ._data import DataURIPath as DataURIPath
    from ._dav import DAVURIPath as DAVURIPath
    from ._file import FileURIPath as FileURIPath
    from ._ftp import BaseFTPURIBackend as BaseFTPURIBackend
    from ._ftp import FTPURIBackend as FTPURIBackend
    from ._ftp import FTPURIPath as FTPURIPath
    from ._git import GitHubGitURIPath as GitHubGitURIPath
    from ._git import GitLabGitURIPath as GitLabGitURIPath
    from ._git import GitURIPath as GitURIPath
    from ._github import GitHubURIPath as GitHubURIPath
    from ._gitlab import GitLabURIPath as GitLabURIPath
    from ._gitrepo import BaseRepoBackend as BaseRepoBackend
    from ._gitrepo import RepoBackend as RepoBackend
    from ._http._backend import HTTPBackend as HTTPBackend
    from ._http._path import HTTPURIPath as HTTPURIPath
    from ._http._streams import HTTPAppendStream as HTTPAppendStream
    from ._http._streams import HTTPWriteStream as HTTPWriteStream

#: Public name -> the private submodule that defines it, loaded on first use.
_EXPORTS = {
    "ArchiveTarURIPath": "_archive",
    "ArchiveURIPath": "_archive",
    "ArchiveZipURIPath": "_archive",
    "TarURIPath": "_archive",
    "ZipURIPath": "_archive",
    "DataURIPath": "_data",
    "DAVURIPath": "_dav",
    "FileURIPath": "_file",
    "BaseFTPURIBackend": "_ftp",
    "FTPURIBackend": "_ftp",
    "FTPURIPath": "_ftp",
    "GitHubGitURIPath": "_git",
    "GitLabGitURIPath": "_git",
    "GitURIPath": "_git",
    "GitHubURIPath": "_github",
    "GitLabURIPath": "_gitlab",
    "BaseRepoBackend": "_gitrepo",
    "RepoBackend": "_gitrepo",
    "HTTPAppendStream": "_http._streams",
    "HTTPBackend": "_http._backend",
    "HTTPURIPath": "_http._path",
    "HTTPWriteStream": "_http._streams",
}

__all__ = [
    "ArchiveTarURIPath",
    "ArchiveURIPath",
    "ArchiveZipURIPath",
    "BaseFTPURIBackend",
    "BaseRepoBackend",
    "DAVURIPath",
    "DataURIPath",
    "DelegatingURIPath",
    "DerivedBackend",
    "FTPURIBackend",
    "FTPURIPath",
    "FileURIPath",
    "GitHubGitURIPath",
    "GitHubURIPath",
    "GitLabGitURIPath",
    "GitLabURIPath",
    "GitURIPath",
    "HTTPAppendStream",
    "HTTPBackend",
    "HTTPURIPath",
    "HTTPWriteStream",
    "MEMBER_SPOOL_BYTES",
    "RepoBackend",
    "TarURIPath",
    "ZipURIPath",
]


class _Module(_types.ModuleType):
    """The module, with the setting that is read where it takes effect
    (`MEMBER_SPOOL_BYTES` in `pathlib_next.archive`) read from and written to
    there."""

    @property
    def MEMBER_SPOOL_BYTES(self) -> int:
        from pathlib_next import archive

        return archive.MEMBER_SPOOL_BYTES

    @MEMBER_SPOOL_BYTES.setter
    def MEMBER_SPOOL_BYTES(self, value: int) -> None:
        from pathlib_next import archive

        archive.MEMBER_SPOOL_BYTES = value


_sys.modules[__name__].__class__ = _Module


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
