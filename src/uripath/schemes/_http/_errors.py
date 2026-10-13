from __future__ import annotations

import contextlib as _contextlib
import errno as _errno
import os as _os

from ._headers import peer_text
from ._status import HTTPStatusError as _HTTPStatusError

_ERRNOS = {
    FileNotFoundError: _errno.ENOENT,
    PermissionError: _errno.EACCES,
    FileExistsError: _errno.EEXIST,
    IsADirectoryError: _errno.EISDIR,
    NotADirectoryError: _errno.ENOTDIR,
}


def _path_error(error_cls, path_obj) -> OSError:
    """`error_cls` built as pathlib builds it -- `(errno, strerror,
    filename)` -- so `e.errno` and `e.filename` are set."""
    code = _ERRNOS.get(error_cls, _errno.EIO)
    return error_cls(code, _os.strerror(code), str(path_obj))


def _server_size(text: "str | None") -> "int | None":
    """A byte count a server stated (`Content-Length`, `getcontentlength`) as
    an int, or `None` when it is not a plain non-negative decimal number."""
    text = (text or "").strip()
    if text.isascii() and text.isdigit() and len(text) <= 19:
        return int(text)
    return None


@_contextlib.contextmanager
def _translate_http_errors(path_obj, *, conflict=FileExistsError):
    """Map a failed request to a pathlib exception for `path_obj`.
    `conflict` is what a 409 means: for a write (PUT, MKCOL, MOVE) RFC 4918
    uses 409 for a missing parent collection, so writers pass
    FileNotFoundError."""
    # `from None`: a chained cause is printed by every traceback, and a
    # transport's own error must not be what a log shows. The status or the
    # exception type stays in the message.
    try:
        yield
    except _HTTPStatusError as e:
        response = e.response
        status = response.status
        reason = peer_text(response.reason or "")
        if status in (404, 410):
            raise _path_error(FileNotFoundError, path_obj) from None
        elif status in (401, 403):
            raise _path_error(PermissionError, path_obj) from None
        elif status == 409:
            raise _path_error(conflict, path_obj) from None
        elif status in (405, 501):
            raise PermissionError(
                _errno.EACCES,
                f"Method not allowed (HTTP {status})",
                str(path_obj),
            ) from None
        else:
            raise OSError(
                _errno.EIO,
                f"HTTP Error {status} {reason}".rstrip() + f" for {path_obj}",
            ) from None
    except TimeoutError as e:
        raise TimeoutError(f"Timeout for {path_obj} ({type(e).__name__})") from None
    except ConnectionError as e:
        raise ConnectionError(
            f"Connection error for {path_obj} ({type(e).__name__})"
        ) from None
