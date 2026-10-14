from __future__ import annotations

import typing as _ty

from pathapi.http import HTTPClient, HTTPResponse, split_userinfo

from ..._version import __version__
from .._path import DerivedBackend
from . import _settings

if _ty.TYPE_CHECKING:
    from ._path import HTTPURIPath


_UNSET = object()
"""The `timeout` of a call that did not give one: the backend's own."""


class HTTPBackend(HTTPClient):
    """The transport and the settings shared by an `HTTPURIPath` tree (see
    `with_transport()` and `with_session()`): a `pathapi.http.HTTPClient`
    that takes a path or a URL for its address and adds `write_method` and
    `append_mode`.

    `transport` is any object with a `send()` method as
    `pathapi.http.HTTPTransport.send()`; without one the backend builds the
    built-in `HTTPTransport` on first use and closes it with `close()` or at the
    end of a `with` block. A transport it was given stays the caller's.
    `headers` are sent with every request, request-specific headers merged
    over them by name; every request gets `timeout=(10, 60)` seconds unless
    `timeout` here or in the call says otherwise (`None` waits without limit).
    URL userinfo (`http://user:password@host/`) is never sent inside the
    request URL: it is stripped and sent as an `Authorization: Basic` header
    unless `headers` or the call name one.

    The backend, through `HTTPClient`, follows redirects. `GET`, `HEAD` and
    `OPTIONS` follow up to 30; a redirect that changes the scheme, host or
    port drops `Authorization` (and nothing else). Any other method
    (`PROPFIND`, `PUT`, `PATCH`, `DELETE`, `MKCOL`, `MOVE`, a `write_method`
    such as `POST`) is sent without following: a 307 or 308 (for `PROPFIND` also
    a 301, 302 or 303) to the same scheme, host and port is sent once more
    with the same method and body, and any other 3xx, a redirect to another
    origin or a second redirect raises `OSError(EIO)`."""

    __slots__ = ("write_method", "append_mode")

    def __init__(
        self,
        transport=None,
        *,
        headers=None,
        timeout=_settings.DEFAULT_TIMEOUT,
        write_method: str = "PUT",
        append_mode: str = "rewrite",
    ):
        super().__init__(
            transport,
            headers=headers,
            timeout=timeout,
            user_agent=f"uripath/{__version__}",
        )
        self.write_method = write_method
        self.append_mode = append_mode

    def __repr__(self) -> str:
        return f"{type(self).__name__}(write_method={self.write_method!r})"

    def request(
        self,
        method,
        uri: "HTTPURIPath|str",
        *,
        data=None,
        headers=None,
        stream: bool = False,
        allow_redirects=None,
        timeout=_UNSET,
    ) -> HTTPResponse:
        """Send `method` to `uri` and return the final response. A `data`
        that is not `bytes` (a file, an iterable) cannot be sent twice, so it
        is not re-sent after a redirect or a dropped connection.
        `allow_redirects=False` returns the first answer of a `GET`, `HEAD`
        or `OPTIONS` as it is. `ValueError` for a URL or header with a control
        character, before anything is sent.

        With `stream=False` the body is read before this returns, and a decoded
        body over `pathapi.http.MAX_REPLY_BYTES` is `OSError(EFBIG)`; with
        `stream=True` the caller reads it, and closes the response."""
        url, auth = split_userinfo(uri if isinstance(uri, str) else uri.as_uri(False))
        return super().request(
            method,
            url,
            data=data,
            headers=headers,
            stream=stream,
            allow_redirects=allow_redirects,
            timeout=self.timeout if timeout is _UNSET else timeout,
            auth=auth,
        )

    def redirect(
        self,
        method,
        uri: "HTTPURIPath|str",
        resp: HTTPResponse,
        *,
        headers=None,
        stream: bool = False,
        timeout=_UNSET,
    ) -> HTTPResponse:
        """Send `method` to where `resp`, the answer to a request for `uri`,
        redirects to, and follow what it redirects to in turn. The request
        carries what `uri` is sent with, except that `Authorization` is left
        off whenever it goes to another scheme, host or port than `uri`'s.
        A redirect with no usable `Location` is `OSError(EIO)`."""
        url, auth = split_userinfo(uri if isinstance(uri, str) else uri.as_uri(False))
        return super().redirect(
            method,
            url,
            resp,
            headers=headers,
            stream=stream,
            timeout=self.timeout if timeout is _UNSET else timeout,
            auth=auth,
        )


class _DerivedHTTPBackend(HTTPBackend, DerivedBackend):
    """What `HTTPURIPath._initbackend()` returns: the class itself says the path
    derived this backend for itself (see `URIPath._supplied_backend()`)."""

    __slots__ = ()
