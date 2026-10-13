from __future__ import annotations

import errno as _errno
import os as _os
import re as _re
import typing as _ty
import urllib.parse as _urlparse

from pathlib_next import FileStat
from pathlib_next import providers as _providers
from .. import _elsewhere, _httpdate
from .._path import URIPath
from . import _follow, _settings
from ._backend import HTTPBackend, _DerivedHTTPBackend
from ._errors import _path_error, _server_size, _translate_http_errors
from ._headers import _IDENTITY_ENCODING
from ._listing import _DirectoryListingParser, _FileEntry
from ._response import HTTPResponse
from ._status import drop_body as _drop_body
from ._status import raise_for_status as _raise_for_status
from ._streams import (
    HTTPAppendStream,
    HTTPWriteStream,
    _ResponseReader,
    _accept,
    _charset,
    _response_reader,
)

_CHUNK = 64 * 1024


# A listing is parsed only from an HTML reply (or one with no Content-Type).
_LISTING_TYPES = ("text/html", "application/xhtml+xml")


_RE_URL_SCHEME = _re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")


class HTTPURIPath(URIPath):
    """`http`/`https` scheme: read/write access over HTTP (`PUT`/`DELETE`
    for writes/deletes, configurable via `with_transport()`), listing
    directories by scraping an Apache/nginx-style HTML index with a
    zero-dependency in-house parser (`_DirectoryListingParser`). Needs no
    third-party library: requests go through `HTTPTransport` unless a
    transport is given."""

    __SCHEMES = ("http", "https")
    __slots__ = ()

    if _ty.TYPE_CHECKING:
        backend: HTTPBackend

    def _initbackend(self):
        return _DerivedHTTPBackend(timeout=_settings.DEFAULT_TIMEOUT)

    def _listdir(self) -> list[_FileEntry]:
        # The slash form first: a server redirects a directory's slash-less URL to it, at a
        # round trip per listing. One that answers 404 for it (a file, or a server that
        # serves the bare path only) is asked again for the path as given.
        slashed = self if self.path.endswith("/") else self.with_path(self.path + "/")
        try:
            req = self._get(slashed)
        except FileNotFoundError:
            if slashed is self:
                raise
            req = self._get(self)
        try:
            content_type = req.headers.get("Content-Type") or ""
            mime = content_type.split(";", 1)[0].strip().lower()
            if mime and mime not in _LISTING_TYPES:
                # A file: pathlib's iterdir() raises, and its body -- maybe
                # gigabytes -- is never downloaded to look for links.
                raise _path_error(NotADirectoryError, self)
            text = self._read_listing(req)
        finally:
            req.close()
        # Scoped by the URL actually answered (after redirects), not by the
        # page's own <title>.
        parser = _DirectoryListingParser(base_url=req.url)
        parser.feed(text)
        parser.close()
        return parser.listing

    def _read_listing(self, req: HTTPResponse) -> str:
        """The body of the directory index `req` as text, read the way
        `open()` reads a file: a cut-short, stalled or undecodable body
        raises `TimeoutError`/`OSError` naming the path, and one longer than
        `MAX_LISTING_BYTES` raises `OSError(EFBIG)`."""
        limit = _settings.MAX_LISTING_BYTES
        too_large = OSError(
            _errno.EFBIG,
            f"Directory index of {self} is larger than {limit} bytes "
            "(MAX_LISTING_BYTES)",
        )
        stated = _server_size(req.headers.get("Content-Length"))
        if stated is not None and stated > limit:
            raise too_large
        reader = _ResponseReader(self, req, _CHUNK)
        chunks = []
        size = 0
        while chunk := reader.read(_CHUNK):
            size += len(chunk)
            if size > limit:
                raise too_large
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            return body.decode(_charset(req.headers), "replace")
        except LookupError:
            return body.decode("utf-8", "replace")

    def _get(self, uri, **kwargs) -> HTTPResponse:
        """A streamed `GET` of `uri` that succeeded, its body unread. A
        failure is translated to the pathlib exception for this path, and the
        connection is released first: `stream=True` leaves it held."""
        with _translate_http_errors(self):
            req = self.backend.request("GET", uri, stream=True, **kwargs)
            try:
                _raise_for_status(req)
            except BaseException:
                _drop_body(req, _settings.MAX_LISTING_BYTES)
                raise
        return req

    def _scandir(self):
        # `_listdir()`'s single GET already carries type/size/mtime for
        # every child -- reuse it instead of `iterdir()` + a HEAD per child.
        for entry in self._listdir():
            # A subdirectory entry carries a trailing "/" (htmllistparse's name is "sub/"):
            # strip it, or the child's path ends in "/" and `Pathname.name` (the last segment)
            # is "".
            is_dir = entry.name.endswith("/")
            name = entry.name.removesuffix("/")
            if not _providers.is_safe_child_name(name):
                # A listing is untrusted: wsgidav renders its parent row as `<a href="..">` and a
                # `<pre>` index can carry `./`. "." or ".." as a child would make `unlink()` DELETE
                # the parent collection and `walk()` loop forever. Filtered here for every parser.
                continue
            if is_dir:
                stat = FileStat(
                    st_size=0, st_mtime=_httpdate.parsedate(entry.modified), is_dir=True
                )
            elif entry.size is not None and entry.size_exact and entry.modified:
                stat = FileStat(
                    st_size=entry.size,
                    st_mtime=_httpdate.parsedate(entry.modified),
                    is_dir=False,
                )
            else:
                # No exact byte count or no date in the listing (the stdlib `<ul>` index, a "1.2K"
                # column): the entry is a file, but a size or time would be made up, so the hint is
                # type-only and `stat()` asks the server.
                stat = FileStat(is_dir=False, size_known=False)
            yield name, stat

    def _is_dir(self, resp: HTTPResponse):
        # Judged on the FINAL response, after redirects (http->https, CDN and "latest"
        # download links redirect to files), by the path of that URL: a query or fragment
        # does not make a directory a file.
        return _urlparse.urlsplit(resp.url).path.endswith(("/", "/..", "/."))

    def stat(self, *, follow_symlinks=True, walk_up_last_modified=False):
        hint = self._pop_stat_hint()
        if hint is not None:
            return hint
        return self._head_stat(walk_up_last_modified)[0]

    def _head_stat(self, walk_up_last_modified=False) -> "tuple[FileStat, bool]":
        """`stat()` without the listing hint, and whether the server stated
        the size: a file whose HEAD reply has no `Content-Length` reports
        `st_size` 0, which is not its length."""
        with _translate_http_errors(self):
            # The caller's own spelling first: a trailing-slash path the
            # server answers is a directory, even when the slash-less URL
            # answers too (wsgidav serves both `/d` and `/d/` with 200).
            check = (
                [self, self.with_path(self.path.removesuffix("/"))]
                if self.path.endswith("/")
                else [self]
            )
            for uri in check:
                resp = self.backend.request(
                    "HEAD", uri, allow_redirects=False, headers=_IDENTITY_ENCODING
                )
                resp.close()
                if resp.status == 405:
                    # Some servers reject HEAD outright; fall back to GET.
                    resp = self.backend.request(
                        "GET",
                        uri,
                        allow_redirects=False,
                        stream=True,
                        headers=_IDENTITY_ENCODING,
                    )
                    resp.close()
                if resp.status < 400:
                    break

            if _follow.is_redirect(resp):
                # Where the first answer pointed, not the same request again;
                # `redirect()` knows the origin that `Authorization` is for.
                moved = resp
                resp = self.backend.redirect(
                    "HEAD", uri, moved, headers=_IDENTITY_ENCODING
                )
                resp.close()
                if resp.status == 405:
                    # The HEAD-405 fallback again after a redirect: a server or proxy that rejects HEAD
                    # everywhere would otherwise raise PermissionError for an existing path.
                    resp = self.backend.redirect(
                        "GET", uri, moved, stream=True, headers=_IDENTITY_ENCODING
                    )
                    resp.close()
            _raise_for_status(resp)
            # From the final URL, once any redirect has been followed.
            is_dir = self._is_dir(resp)

        # A missing, non-numeric or negative Content-Length is no size.
        stated = None if is_dir else _server_size(resp.headers.get("Content-Length"))
        st_size = stated or 0
        lm = resp.headers.get("Last-Modified")
        if lm is None and walk_up_last_modified:
            parent = self.parent
            if self != parent:
                try:
                    entry = next(
                        filter(
                            lambda p: p.name.removesuffix("/") == self.name,
                            parent._listdir(),
                        )
                    )
                    if entry and entry.modified:
                        lm = entry.modified
                except (StopIteration, OSError):
                    pass

        size_stated = is_dir or stated is not None
        stat = FileStat(
            st_size=st_size, st_mtime=_httpdate.parsedate(lm), is_dir=is_dir
        )
        return stat, size_stated

    def _ensure_missing(self) -> None:
        """Raise `FileExistsError` unless `stat()` says the path is not
        found. Any other failure of the probe (a 5xx, a 403, a timeout)
        propagates: it must not read as permission to create."""
        try:
            self.stat()
        except FileNotFoundError:
            return
        raise _path_error(FileExistsError, self)

    def _open(
        self,
        mode="r",
        buffering=-1,
    ):
        if mode == "r":
            req = self._get(self.as_uri(), headers=_IDENTITY_ENCODING)
            return _response_reader(self, req, buffering)
        if mode == "a":
            return HTTPAppendStream(self)
        if mode not in ("w", "x"):
            raise NotImplementedError(f"open(mode={mode!r})")
        if mode == "x":
            self._ensure_missing()
        return HTTPWriteStream(self, exclusive=mode == "x")

    def unlink(self, missing_ok=False):
        # A server that honours DELETE on a collection (WebDAV, RFC 4918) removes the whole
        # tree, and unlink() never removes a directory: refuse one. Over http: this uses the
        # HEAD `stat()` heuristic, which misses some collections (see `dav:` for reliable ones).
        if self.is_dir():
            raise IsADirectoryError(
                _errno.EISDIR, _os.strerror(_errno.EISDIR), str(self)
            )
        self._delete(missing_ok=missing_ok)

    def _delete(self, missing_ok=False):
        # The raw DELETE, with no collection guard: `rmdir()` has already
        # verified an empty directory before calling it.
        with _translate_http_errors(self):
            resp = self.backend.request("DELETE", self, stream=True)
            if resp.status == 404:
                _drop_body(resp, _settings.MAX_LISTING_BYTES)
                if missing_ok:
                    return
                raise FileNotFoundError(self)
            _accept(resp)

    def rmdir(self):
        # An empty directory's listing and a file whose body parses to zero entries look
        # alike from `_listdir()`: without this check rmdir() of a file would DELETE it
        # instead of raising NotADirectoryError.
        if not self.is_dir():
            raise NotADirectoryError(self)
        # `_scandir()`, not the raw `_listdir()`: a listing's own "."/".."
        # rows are not children and must not make an empty directory
        # look non-empty.
        for _ in self._scandir():
            raise OSError(_errno.ENOTEMPTY, "Directory not empty", str(self))
        self._delete()

    def with_transport(
        self,
        transport,
        *,
        headers=None,
        timeout=_settings.DEFAULT_TIMEOUT,
        write_method: str = "PUT",
        append_mode: str = "rewrite",
    ):
        """This path with a backend that sends through `transport` (any object
        with a `send()` method as `HTTPTransport.send()`; the caller closes
        it). `headers` go with every request; `write_method` (`"PUT"`, or
        e.g. `"POST"`) uploads on close, and `append_mode` is `"rewrite"` or
        `"patch"`."""
        backend = HTTPBackend(
            transport,
            headers=headers,
            timeout=timeout,
            write_method=write_method,
            append_mode=append_mode,
        )
        return type(self)(self, backend=backend)

    def with_session(
        self,
        session,
        write_method: str = "PUT",
        append_mode: str = "rewrite",
        **requests_args,
    ):
        """This path with a backend that sends through a `requests.Session`.
        That transport is provided by the `uripath-http-requests`
        distribution: without it this raises `ImportError` naming it."""
        raise _elsewhere.requests_transport_missing()
