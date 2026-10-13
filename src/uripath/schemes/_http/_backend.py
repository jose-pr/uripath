from __future__ import annotations

import typing as _ty

from .._path import DerivedBackend
from . import _follow, _settings
from ._follow import FOLLOWED_METHODS as _FOLLOWED_METHODS
from ._follow import basic_authorization as _basic_authorization
from ._follow import split_userinfo as _split_userinfo
from ._headers import check_headers as _check_headers
from ._headers import check_url as _check_url
from ._headers import has_header as _has_header
from ._headers import merge_headers as _merge_headers
from ._response import HTTPResponse
from ._select import TransportOwner
from ._status import too_large as _too_large

if _ty.TYPE_CHECKING:
    from ._path import HTTPURIPath


_UNSET = object()
"""The `timeout` of a call that did not give one: the backend's own."""


_BASE_HEADERS = {"User-Agent": "uripath", "Accept": "*/*"}


class HTTPBackend(TransportOwner):
    """The transport and the settings shared by an `HTTPURIPath` tree (see
    `with_transport()` and `with_session()`).

    `transport` is any object with a `send()` method as
    `HTTPTransport.send()`; without one the backend builds the built-in
    `HTTPTransport` on first use and closes it with `close()` or at the
    end of a `with` block. A transport it was given stays the caller's.
    `headers` are sent with every request, request-specific headers merged
    over them by name; every request gets `timeout=DEFAULT_TIMEOUT`
    (`(10, 60)` seconds) unless `timeout` here or in the call says otherwise
    (`None` waits without limit). URL userinfo (`http://user:password@host/`)
    is never sent inside the request URL: it is stripped and sent as an
    `Authorization: Basic` header unless `headers` or the call name one.

    This backend, not the transport, follows redirects. `GET`, `HEAD` and
    `OPTIONS` follow up to 30; a redirect that changes the scheme, host or
    port drops `Authorization` (and nothing else). Any other method
    (`PROPFIND`, `PUT`, `PATCH`, `DELETE`, `MKCOL`, `MOVE`, a `write_method`
    such as `POST`) is sent without following: a 307 or 308 (for `PROPFIND` also
    a 301, 302 or 303) to the same scheme, host and port is sent once more
    with the same method and body, and any other 3xx, a redirect to another
    origin or a second redirect raises `OSError(EIO)`."""

    __slots__ = ("headers", "timeout", "write_method", "append_mode", "__weakref__")

    def __init__(
        self,
        transport=None,
        *,
        headers=None,
        timeout=_settings.DEFAULT_TIMEOUT,
        write_method: str = "PUT",
        append_mode: str = "rewrite",
    ):
        super().__init__(transport)
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.write_method = write_method
        self.append_mode = append_mode

    def __repr__(self) -> str:
        return f"{type(self).__name__}(write_method={self.write_method!r})"

    def _prepared(self, uri, headers) -> "tuple[str, dict]":
        """The URL without userinfo, and the headers every request to `uri`
        starts from: the base ones, the backend's, the call's, and the
        `Authorization: Basic` that the userinfo stands for."""
        url, auth = _split_userinfo(uri if isinstance(uri, str) else uri.as_uri(False))
        sent = _merge_headers(_BASE_HEADERS, self.headers, headers)
        if auth is not None and not _has_header(sent, "Authorization"):
            sent["Authorization"] = _basic_authorization(auth)
        return url, sent

    def _dispatch(
        self, method, url, sent, data, allow_redirects, stream, timeout, first=None
    ) -> HTTPResponse:
        _check_url(url)
        _check_headers(sent)
        if timeout is _UNSET:
            timeout = self.timeout
        if isinstance(data, str):
            data = data.encode("utf-8")
        transport = self.transport
        # Always streamed from the transport, so that no reply is read whole
        # before it is known to be small enough (see `stream` below).
        if method.upper() in _FOLLOWED_METHODS and data is None:
            if allow_redirects is False and first is None:
                resp = transport.send(
                    method, url, headers=sent, timeout=timeout, stream=True
                )
            else:
                resp = _follow.send_following(
                    transport,
                    method,
                    url,
                    headers=sent,
                    timeout=timeout,
                    stream=True,
                    first=first,
                )
        else:
            resp = _follow.send_once(
                transport,
                method,
                url,
                headers=sent,
                body=data,
                timeout=timeout,
                stream=True,
            )
        if not stream:
            limit = _settings.MAX_LISTING_BYTES
            resp._buffered(limit, _too_large(_follow.shown(url), limit))
        return resp

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
        body over `MAX_LISTING_BYTES` is `OSError(EFBIG)`; with `stream=True`
        the caller reads it, and closes the response."""
        url, sent = self._prepared(uri, headers)
        return self._dispatch(method, url, sent, data, allow_redirects, stream, timeout)

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
        url, sent = self._prepared(uri, headers)
        location = _follow.redirect_location(url, resp)
        if location is None:
            raise _follow.refused_redirect(
                method, url, resp, None, "no usable Location"
            )
        return self._dispatch(
            method, location, sent, None, None, stream, timeout, first=url
        )


class _DerivedHTTPBackend(HTTPBackend, DerivedBackend):
    """What `HTTPURIPath._initbackend()` returns: the class itself says the path
    derived this backend for itself (see `URIPath._supplied_backend()`)."""

    __slots__ = ()
