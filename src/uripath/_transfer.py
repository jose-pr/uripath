"""`copy_stream`: the bytes of a path or a binary stream into another."""

from __future__ import annotations

import errno as _errno
import os as _os
import shutil as _shutil
import typing as _ty

from pathapi import Path

from ._pathtext import as_path
from .exceptions import OutputClosedError

__all__ = ["copy_stream"]

#: Bytes read and written at a time.
_CHUNK_SIZE = 1024 * 1024

#: Windows reports a write to a pipe whose reader has gone as EINVAL.
_WINDOWS = _os.name == "nt"

_Endpoint = _ty.Union[str, "_os.PathLike[str]", Path, _ty.BinaryIO]


def _is_closed_pipe(error: OSError) -> bool:
    return isinstance(error, BrokenPipeError) or (
        _WINDOWS and error.errno == _errno.EINVAL
    )


class _PipeWriter:
    """Writes to a stream the caller owns, turning a closed pipe there into
    `OutputClosedError`."""

    __slots__ = ("_stream",)

    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        try:
            return self._stream.write(data)
        except OSError as error:
            if _is_closed_pipe(error):
                raise OutputClosedError(error.errno, "output closed") from error
            raise

    def flush(self):
        try:
            self._stream.flush()
        except OSError as error:
            if _is_closed_pipe(error):
                raise OutputClosedError(error.errno, "output closed") from error
            raise


def _path_of(endpoint) -> Path:
    if isinstance(endpoint, Path):
        return endpoint
    if isinstance(endpoint, str):
        return as_path(endpoint)
    if isinstance(endpoint, _os.PathLike):
        return as_path(_os.fspath(endpoint))
    raise TypeError(
        "expected a path, path text or a binary stream, "
        f"not {type(endpoint).__name__!r}"
    )


def _copy(reader, target, exclusive: bool, chunk_size: int) -> None:
    if callable(getattr(target, "write", None)):
        writer = _PipeWriter(target)
        _shutil.copyfileobj(reader, writer, chunk_size)
        writer.flush()
        return
    with _path_of(target).open("xb" if exclusive else "wb") as writer:
        _shutil.copyfileobj(reader, writer, chunk_size)


def copy_stream(
    source: _Endpoint,
    target: _Endpoint,
    *,
    exclusive: bool = False,
    chunk_size: int = _CHUNK_SIZE,
) -> None:
    """Copy the bytes of `source` to `target`, `chunk_size` at a time, never
    holding the whole object in memory.

    Each end is a binary stream (anything with `read()` or `write()`), a path
    object, or text that `as_path()` turns into a path. A path is opened here
    and closed when the copy ends; a stream stays open and is the caller's.
    The target stream is flushed at the end.

    `exclusive` refuses a target path that exists (`FileExistsError`), as an
    exclusive create does: there is no check-then-write race. A target stream
    has nothing to refuse.

    A target stream whose reader went away (a pipe whose other end closed,
    which Windows reports as `OSError(EINVAL)`) raises `OutputClosedError`.
    The same error from the connection of a path is not translated.
    """
    if callable(getattr(source, "read", None)):
        _copy(source, target, exclusive, chunk_size)
        return
    with _path_of(source).open("rb") as reader:
        _copy(reader, target, exclusive, chunk_size)
