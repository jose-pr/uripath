from __future__ import annotations

import ipaddress as _ip
import typing as _ty

from .. import _rfc3986
from ..exceptions import URISyntaxError

_IPAddress = _ty.Union[_ip.IPv4Address, _ip.IPv6Address]


_DIGITS = "0123456789"


#: Error handler for percent-escapes. A valid URI may escape bytes that are not
#: UTF-8 (`caf%E9.html`); `surrogateescape` carries each through the decoded `str`
#: and back out to the same escape, where `strict` would raise UnicodeDecodeError.
ERRORS = "surrogateescape"
_ERRORS = ERRORS


class _Userinfo(str):
    """A decoded userinfo that remembers which colon separated the user name
    from the password. It equals, hashes and prints as the plain
    `user:password` text, so code that treats `Source.userinfo` as a `str`
    is unaffected; only the composer and `Source.parsed_userinfo()` read
    the split. Without it a user name holding an escaped colon (`us%3Aer`)
    could not be told from a password separator once decoded."""

    __slots__ = ("user", "password")

    def __new__(cls, user: str, password: "str | None" = None):
        obj = str.__new__(cls, user if password is None else f"{user}:{password}")
        obj.user = user
        obj.password = password
        return obj

    def __reduce__(self):
        return _Userinfo, (self.user, self.password)


def _split_userinfo_text(userinfo: str) -> "tuple[str, str | None]":
    """`(user, password)` of a userinfo: the split `_Userinfo` recorded, else
    at the first colon. `password` is None when there is no colon."""
    if isinstance(userinfo, _Userinfo):
        return userinfo.user, userinfo.password
    user, colon, password = userinfo.partition(":")
    return user, (password if colon else None)


def _decode_userinfo(raw: str) -> _Userinfo:
    """Decode a raw userinfo: split at the first literal colon FIRST, then
    decode each half, so an escaped `%3A` stays part of the name."""
    user, colon, password = raw.partition(":")
    return _Userinfo(
        _rfc3986.decode(user, _ERRORS),
        _rfc3986.decode(password, _ERRORS) if colon else None,
    )


def _parse_port(text: str) -> "int | None":
    """The port a run of ASCII digits names (None for no digits), which must
    be 0-65535 (RFC 3986 3.2.3 leaves it open; TCP and UDP do not). The
    message names no part of the input: it may sit beside a password."""
    if not text:
        return None
    digits = text.lstrip("0") or "0"
    if len(digits) > 5 or int(digits) > 65535:
        raise URISyntaxError("port out of range 0-65535")
    return int(digits)


def _split_authority(
    authority: "str | None",
) -> "tuple[str | None, str | None, int | None]":
    """One-pass split of a raw URI authority into (userinfo, host, port) --
    RAW/undecoded strings, port as int-or-None. It follows the RFC 3986
    reading of `userinfo@host:port` with one split of the authority; the tests
    compare it with the `uritools` reading and name where it differs:

    * a host is followed by a port only when a ':' was found, so a host of
      digits alone (`s3://20240101/key`) stays the host, where `uritools`
      reads it as a port and returns an empty host;
    * the port is 0-65535; a ':' followed by anything else that is not a
      bracketed address is an invalid port (`URISyntaxError`), not part of the
      host name."""
    if authority is None:
        return None, None, None
    userinfo, at_sep, hostinfo = authority.rpartition("@")
    if not at_sep:
        userinfo = None
    host, colon, tail = hostinfo.rpartition(":")
    if colon and not tail.lstrip(_DIGITS):
        return userinfo, host, _parse_port(tail)
    if colon and not hostinfo.startswith("["):
        raise URISyntaxError("invalid port: it must be digits")
    return userinfo, hostinfo, None


def _ipv6_from_literal(literal: str) -> _ip.IPv6Address:
    """The address a bracketed IPv6 literal names. A zone is introduced by
    `%25` (RFC 6874: the `%` of `address%zone` is escaped inside a URI) and
    is percent-decoded; a bare `%` is read as the delimiter as well, as
    `ipaddress` does."""
    address, sep, zone = literal.partition("%25")
    if sep:
        literal = f"{address}%{_rfc3986.decode(zone, _ERRORS)}"
    try:
        return _ip.IPv6Address(literal)
    except ValueError:
        raise URISyntaxError("invalid IPv6 address in the host") from None


def _decode_host(host: str) -> "str | _IPAddress":
    """Decode a raw (still percent-encoded) host string. A bracketed
    literal is an IPv6 address; mismatched brackets and a literal that starts
    with a lower-case `v` (an IPvFuture version flag; RFC 3986 spells it in
    either case, and only the lower-case one is refused) raise
    `URISyntaxError`; a dotted quad is an IPv4 address; anything else is a
    name, percent-decoded. An IPv6 zone is read as RFC 6874 says
    (`_ipv6_from_literal`)."""
    if host.startswith("[") and host.endswith("]"):
        literal = host[1:-1]
        if literal.startswith("v"):
            raise URISyntaxError("address mechanism not supported")
        return _ipv6_from_literal(literal)
    if host.startswith("[") or host.endswith("]"):
        raise URISyntaxError(f"Invalid host {host!r}: mismatched brackets")
    try:
        return _ip.IPv4Address(host)
    except ValueError:
        return _rfc3986.decode(host, _ERRORS)


def fold_host(host: "str | _IPAddress | None") -> "str | _IPAddress | None":
    """`host` as a comparison or a key reads it: a name in lower case, since
    host names are case-insensitive (RFC 3986 3.2.2), and an address as it is.
    `Source.host` keeps the spelling it was given, so anything that compares
    hosts or uses one as a key folds it at that place."""
    return host.lower() if isinstance(host, str) else host


def is_drive(segment: str) -> bool:
    """Whether a path segment is a Windows drive ("C:")."""
    return len(segment) == 2 and segment[1] == ":" and segment[0].isalpha()


_is_drive = is_drive


def _remove_dot_segments(path: str, *, drive: bool = False) -> str:
    """RFC 3986 5.2.4 dot-segment removal on a path. Apply it to a raw
    (still percent-encoded) path before decoding,
    and again to the decoded path: a `%2e` only becomes a `.` segment
    once decoded. A `..` that would pass the root of an absolute path is
    dropped; a relative path keeps its leading `..`.

    `drive=True` (a `file:` path on Windows) makes a leading drive segment
    ("C:/x", "/C:/x") the anchor, which `..` never climbs above, as for
    `PureWindowsPath`."""
    if drive:
        head = path[1:] if path.startswith("/") else path
        letter, sep, rest = head.partition("/")
        if sep and _is_drive(letter):
            lead = path[: len(path) - len(head)]
            return lead + letter + _remove_dot_segments("/" + rest)
    pseg = []
    for s in path.split("/"):
        if s == ".":
            continue
        elif s != "..":
            pseg.append(s)
        elif len(pseg) == 1 and not pseg[0]:
            continue
        elif pseg and pseg[-1] != "..":
            pseg.pop()
        else:
            pseg.append(s)
    if path.rpartition("/")[2] in (".", ".."):
        pseg.append("")
    if path and len(pseg) == 1 and pseg[0] == "":
        pseg.insert(0, ".")
    return "/".join(pseg)
