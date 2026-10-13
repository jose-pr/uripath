"""`as_path`: text that is a local path or a URI, read as the path it names."""

from __future__ import annotations

import typing as _ty

from pathlib_next import LocalPath

from .schemes._path import URIPath, _looks_like_uri

__all__ = ["as_path"]


def as_path(text: str) -> "_ty.Union[LocalPath, URIPath]":
    """The path `text` names: a `URIPath` when it is a URI, a `LocalPath` when
    it is a local path.

    `text` is a URI when it starts with an RFC 3986 scheme and either holds
    `://` or the scheme is one a class registers (`data:`, `zip:`, `file:`,
    `sftp:`, ...). Anything else is local: `C:/data` (a one-letter scheme is a
    drive), `12:30.txt`, `notes:draft` and `./a:b`. A scheme another
    distribution provides gives a `URIPath` whose first I/O raises the
    `ImportError` that names the distribution to install.

    Raises `TypeError` for what is not a `str`. Nothing is read or connected
    to.
    """
    if not isinstance(text, str):
        raise TypeError(f"path text must be a str, not {type(text).__name__!r}")
    if _looks_like_uri(text):
        return URIPath(text, findclass=True)
    return LocalPath(text)
