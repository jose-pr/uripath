from __future__ import annotations

import typing as _ty

import uritools as _uritools

from ..exceptions import URISyntaxError

from ._compose import _compose_uri
from ._locality import _host_is_local
from ._parse import (
    _decode_host,
    _decode_userinfo,
    _IPAddress,
    _Userinfo,
    _split_authority,
    _split_userinfo_text,
)

if _ty.TYPE_CHECKING:
    from ..schemes._path import URIPath


#: Schemes whose userinfo is an access token, not a user name: `str()` and
#: `repr()` show none of it (the classes drop it from their own text too).
_TOKEN_SCHEMES = frozenset({"github", "gitlab", "git", "git+github", "git+gitlab"})


def _redact_userinfo(userinfo: str, scheme: "str | None") -> "_Userinfo | None":
    """`userinfo` without its password; nothing at all for a token scheme,
    where the user name is the secret. An empty user name leaves no
    userinfo."""
    if scheme in _TOKEN_SCHEMES:
        return None
    user = _split_userinfo_text(userinfo)[0]
    return _Userinfo(user) if user else None


def _source_parts(source: "Source", sanitize: bool) -> tuple:
    """`(scheme, userinfo, host, port)` as `_compose_uri` takes them for
    `source`: falsy fields are left out and `sanitize` drops the password.
    A `Source` and a `URI` both render through this, so they cannot
    disagree."""
    scheme = source.scheme.lower() if source.scheme else None
    userinfo = source.userinfo or None
    if sanitize and userinfo:
        userinfo = _redact_userinfo(userinfo, scheme)
    # An empty host is an empty authority (`file:///x`), which is not no host.
    host = source.host if source.host is not None else None
    port = source.port if source.port not in (None, "") else None
    return scheme, userinfo, host, port


def _parse_source(scheme: "str | None", authority: "str | None") -> "Source":
    """The `Source` of an already split URI: `scheme` is lower-cased by the
    caller, `authority` is the raw text. Used by `URI` and `Source.parse`
    so both read an authority the same way."""
    userinfo, host, port = _split_authority(authority)
    if userinfo is not None:
        userinfo = _decode_userinfo(userinfo)
    host = _decode_host(host) if host is not None else None
    return Source(scheme, userinfo, host, port)


class Source(_ty.NamedTuple):
    """A URI's scheme/userinfo/host/port -- everything before the path.
    Falsy (`bool(source) is False`) when every field is empty/None. A host of
    `""` is an authority with no host (`file:///x`) and `None` is no authority
    (`file:/x`): they render differently and name the same endpoint."""

    scheme: str | None
    userinfo: str | None
    host: str | _IPAddress | None
    port: int | None

    def __bool__(self):
        return (
            (self[0] != "" and self[0] is not None)
            or (self[1] != "" and self[1] is not None)
            or (self[2] != "" and self[2] is not None)
            or (self[3] != "" and self[3] is not None)
        )

    def _redacted_userinfo(self) -> "_Userinfo | None":
        if not self.userinfo:
            return self.userinfo
        scheme = self.scheme.lower() if self.scheme else None
        return _redact_userinfo(self.userinfo, scheme)

    def __str__(self) -> str:
        """The canonical text of this source (`scheme://userinfo@host:port`;
        `file://` for an empty host, `file:` for none), without the password: `str()` is what
        logging and printing reach for, and a `Source` on a failing call stack
        must not leak a credential. It is the composer `URI.as_uri()` uses, so
        a non-ASCII host renders as IDNA, and a scheme or port that is not
        valid raises `ValueError`. `parse(str(source))` is this source except
        for the password; `reveal()` keeps it."""
        scheme, userinfo, host, port = _source_parts(self, True)
        return _compose_uri(scheme, userinfo, host, port, "", None, None)

    def reveal(self) -> str:
        """The text of this source with its password, which `str()` leaves out:
        the credentialed round trip, as `URI.as_uri(sanitize=False)` is for a
        URI. Named as an action because the result carries the secret; it
        belongs in a connection, never in a log or a message."""
        scheme, userinfo, host, port = _source_parts(self, False)
        return _compose_uri(scheme, userinfo, host, port, "", None, None)

    def __repr__(self) -> str:
        # NamedTuple's generated __repr__ shows self.userinfo verbatim, and a traceback
        # frame renders repr(): redact as __str__ does, or a failing call stack leaks it.
        return (
            f"{type(self).__name__}(scheme={self.scheme!r}, "
            f"userinfo={self._redacted_userinfo()!r}, host={self.host!r}, "
            f"port={self.port!r})"
        )

    @classmethod
    def parse(cls, text: str, *, strict: bool = True) -> Source:
        """The `Source` a URI string names. With `strict` (the default) a
        path, query or fragment is a `URISyntaxError` that names the component
        and not the text, which may carry a password. A port outside
        0-65535, or a ':' followed by anything but digits in a name that is
        not a bracketed address, is a `URISyntaxError` as well. `TypeError`
        for what is not a `str`."""
        if not isinstance(text, str):
            raise TypeError(f"source text must be a str, not {type(text).__name__!r}")
        uri = _uritools.urisplit(text)
        if strict:
            extra = [
                name for name in ("path", "query", "fragment") if getattr(uri, name)
            ]
            if extra:
                raise URISyntaxError(
                    "expected scheme and authority only, found a "
                    + " and a ".join(extra)
                )
        scheme = uri.scheme.lower() if uri.scheme is not None else None
        return _parse_source(scheme, uri.authority)

    @classmethod
    def try_parse(
        cls, text: str, default: "Source | None" = None, *, strict: bool = True
    ) -> "Source | None":
        """`parse()`, but `default` (`None`) for text that is not a source.
        `TypeError` still for what is not a `str`."""
        try:
            return cls.parse(text, strict=strict)
        except URISyntaxError:
            return default

    def keys(self):
        return self._asdict().keys()

    def __getitem__(self, key: int | slice | str):
        if isinstance(key, str):
            return getattr(self, key)
        return tuple.__getitem__(self, key)

    def parsed_userinfo(self) -> "tuple[str, str]":
        """`(user, password)`, `""` for a part that is absent. The split is
        the first colon of the userinfo as it was written (an escaped colon
        in the user name stays in the name)."""
        if not self.userinfo:
            return "", ""
        user, password = _split_userinfo_text(self.userinfo)
        return user, password or ""

    def get_scheme_cls(self, schemesmap: _ty.Mapping[str, type["URIPath"]] = None):
        """The `URIPath` subclass registered for this scheme, or `URIPath`
        itself. An explicit `schemesmap` is the complete set of classes to
        choose from: a scheme missing from it gives `URIPath`, and neither
        plugins nor the global registry are consulted."""
        from ..schemes._path import URIPath

        if self.scheme:
            if schemesmap is not None:
                return schemesmap.get(self.scheme, None) or URIPath
            # A scheme no class registers is looked up in the built-in modules and the
            # entry points once; `_load_entry_point` caches that negative answer instead
            # of rescanning every installed distribution on each construction.
            return URIPath._find_scheme(self.scheme) or URIPath
        return URIPath

    def is_local(self) -> bool:
        """Whether `host` resolves to this machine.

        The answer depends on the host alone (userinfo, port and scheme play
        no part) and is remembered for `_LOCAL_TTL` seconds, at most
        `_LOCAL_CACHE_SIZE` hosts: it comes from a DNS/hosts-file lookup and
        the machine's interfaces, so it is neither free nor forever.

        The hostname->address step uses `netimps.resolve()` (default
        backend chain: dnspython, then the OS resolver via
        `getaddrinfo()` -- hosts file, NSS, DNS, OS cache -- then
        `nslookup` as a last resort), trying both `"a"`/`"aaaa"` record
        types and treating `host` as local if ANY resolved address is.
        The "is this address MINE" comparison uses
        `netimps.is_local_address()`, which enumerates the real network
        interfaces (`netimps.get_interfaces()`), so VMs, containers, VPN
        interfaces and additional NICs count.

        `host` as a bare IP-literal `str` (e.g. a directly-constructed
        `Source(..., host="::1", ...)`, bypassing `_decode_host()`'s usual
        bracket-literal parsing) is handled by `netimps.try_parse()`
        without going through resolution at all.
        """
        host = self.host
        if not host or host == "localhost":
            return True
        return _host_is_local(host)


_NOSOURCE = Source(None, None, None, None)


def _port_key(port) -> "int | str | None":
    if port in (None, ""):
        return None
    text = str(port)
    return int(text) if text.isascii() and text.isdigit() else port


def _authority_key(source: Source) -> tuple:
    scheme, userinfo, host, port = source
    return (
        scheme.lower() if scheme else None,
        _split_userinfo_text(userinfo) if userinfo else None,
        str(host).lower() if host else None,
        _port_key(port),
    )


def same_authority(a: Source, b: Source) -> bool:
    """Whether two sources name the same endpoint (scheme, userinfo, host,
    port), treating `""` and `None` alike. The test for whether a backend,
    connection or rename may cross from one path to another."""
    return _authority_key(a) == _authority_key(b)


_same_authority = same_authority
