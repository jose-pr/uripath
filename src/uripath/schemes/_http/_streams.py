from __future__ import annotations

import errno as _errno
import io as _io
import typing as _ty

from pathapi import providers as _providers
from pathapi.http import (
    HTTPResponse,
    drop_body,
    os_error,
    raise_for_status,
    translate_errors,
)

if _ty.TYPE_CHECKING:
    from ._path import HTTPURIPath


def _charset(headers) -> str:
    """The charset a `Content-Type` names, `utf-8` when it names none."""
    for part in (headers.get("Content-Type") or "").split(";")[1:]:
        name, _, value = part.partition("=")
        if name.strip().lower() == "charset":
            return value.strip().strip("\"'") or "utf-8"
    return "utf-8"


class _ResponseReader(_io.RawIOBase):
    """Raw read stream over a streamed response body.

    The transport has decoded a body the server encoded anyway (despite
    `Accept-Encoding: identity`), and a failure in the middle of the body
    surfaces as `TimeoutError`/`ConnectionError`/`OSError` naming the path.
    A decoded chunk larger than the caller's buffer is kept for the next
    `readinto()`."""

    def __init__(self, path, response: HTTPResponse, chunk_size: int):
        super().__init__()
        self._path = path
        self._response = response
        self._chunks = response.iter_bytes(chunk_size)
        self._pending = b""
        self._offset = 0

    def readable(self):
        return True

    def _next_chunk(self) -> bytes:
        path = self._path
        with translate_errors(path):
            try:
                return next(self._chunks, b"")
            except OSError as error:
                if type(error) is OSError and error.errno == _errno.EIO:
                    raise OSError(_errno.EIO, f"{error.strerror} for {path}") from None
                raise

    def readinto(self, buffer):
        view = memoryview(buffer).cast("B")
        if not view:
            return 0
        while self._offset >= len(self._pending):
            chunk = self._next_chunk()
            if not chunk:
                return 0
            self._pending, self._offset = chunk, 0
        count = min(len(view), len(self._pending) - self._offset)
        view[:count] = self._pending[self._offset : self._offset + count]
        self._offset += count
        return count

    def close(self):
        if not self.closed:
            try:
                self._response.close()
            finally:
                super().close()


def _response_reader(path, response: HTTPResponse, buffering: int):
    buffer_size = _io.DEFAULT_BUFFER_SIZE if buffering < 0 else buffering
    raw = _ResponseReader(path, response, buffer_size or _io.DEFAULT_BUFFER_SIZE)
    return raw if buffer_size == 0 else _io.BufferedReader(raw, buffer_size)


_EXCLUSIVE_CREATE = {"headers": {"If-None-Match": "*"}}
"""Request keywords that make a `PUT` create the file only if it is absent
(RFC 9110 13.1.2)."""


class _UploadStream(_providers.DiscardOnError, _io.BytesIO):
    """A write buffer whose `close()` uploads its content through `_upload()`.

    `_ready` is set by a subclass as the last step of its constructor. A
    stream whose constructor raised stays inert: `IOBase.__del__` still calls
    `close()` on it, and that must neither upload a half-built buffer nor
    fail on state the constructor never reached. A `with` block that raised
    through the stream, or collecting it unclosed, discards it
    (`DiscardOnError`): nothing is sent."""

    _ready = False

    def __init__(self, path: "HTTPURIPath"):
        super().__init__()
        self._path = path

    def _upload(self, data: bytes) -> None:
        raise NotImplementedError

    def _holds_uncommitted(self):
        return self._ready

    def discard(self):
        """Drop the buffer: `close()` sends nothing."""
        self._ready = False
        if not self.closed:
            self.truncate(0)

    def close(self):
        if self.closed:
            return
        try:
            if self._ready:
                self._upload(self.getvalue())
        finally:
            # Closed even when the upload fails: a later close() (context
            # manager cleanup, or garbage collection) must not send it again.
            super().close()


class HTTPWriteStream(_UploadStream):
    def __init__(self, path: "HTTPURIPath", exclusive: bool = False):
        super().__init__(path)
        # `exclusive` (mode "x"): the upload carries `If-None-Match: *`, and a
        # 412 reply means the file appeared since the caller looked.
        self._exclusive = exclusive
        self._ready = True

    def _upload(self, data):
        backend = self._path.backend
        extra = _EXCLUSIVE_CREATE if self._exclusive else {}
        with translate_errors(self._path, conflict=FileNotFoundError):
            resp = backend.request(
                backend.write_method,
                self._path.as_uri(),
                data=data,
                stream=True,
                **extra,
            )
            try:
                if self._exclusive and resp.status == 412:
                    raise os_error(FileExistsError, self._path)
                raise_for_status(resp)
            finally:
                drop_body(resp)


class HTTPAppendStream(_UploadStream):
    def __init__(self, path: "HTTPURIPath"):
        super().__init__(path)
        if path.backend.append_mode == "rewrite":
            try:
                existing = path.read_bytes()
            except FileNotFoundError:
                existing = b""
            self.write(existing)
        else:
            # "patch" mode: stat the resource to get its size as start offset.
            # Drop a listing-derived hint first: an offset taken from a hint
            # would overwrite the file wherever the listing was wrong.
            path._pop_stat_hint()
            try:
                stat, size_stated = path._head_stat()
            except FileNotFoundError:
                self._start_offset = 0
                self._existed = False
            else:
                if not size_stated:
                    raise OSError(
                        _errno.EIO,
                        f"Cannot append to {path} in patch mode: the HEAD reply "
                        "has no Content-Length, so the end of the file is unknown",
                    )
                self._start_offset = stat.st_size
                self._existed = True
        self._ready = True

    def _upload(self, data):
        backend = self._path.backend
        with translate_errors(self._path, conflict=FileNotFoundError):
            if backend.append_mode == "rewrite":
                resp = backend.request(
                    backend.write_method, self._path.as_uri(), data=data, stream=True
                )
                _accept(resp)
            else:
                # "patch" mode: send only new content via Content-Range
                if not data:
                    # `bytes N-(N-1)/*` is not a valid range: there is
                    # nothing to append, only a missing file to create.
                    if not self._existed:
                        resp = backend.request(
                            backend.write_method,
                            self._path.as_uri(),
                            data=b"",
                            stream=True,
                        )
                        _accept(resp)
                    return
                start = self._start_offset
                end = start + len(data) - 1
                headers = {"Content-Range": f"bytes {start}-{end}/*"}
                resp = backend.request(
                    "PATCH",
                    self._path.as_uri(),
                    data=data,
                    headers=headers,
                    stream=True,
                )
                _accept(resp)


def _accept(resp: HTTPResponse) -> None:
    """Raise for an error status of `resp`, a reply whose body is not used:
    the body is dropped (see `drop_body`) whichever way this goes."""
    try:
        raise_for_status(resp)
    finally:
        drop_body(resp)
