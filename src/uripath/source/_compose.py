"""Composing URI text from decoded components.

Direct string assembly instead of `uricompose()`'s per-call re-validation, which
only matters for untrusted input: these parts come from a parse or a join.
"""

from __future__ import annotations

import ipaddress as _ip
import re as _re

import uritools as _uritools

from ._parse import (
    ERRORS,
    _IPAddress,
    _ipv6_from_literal,
    _parse_port,
    _split_userinfo_text,
)

_SUB_DELIMS = "!$&'()*+,;="
_SAFE_USER = _SUB_DELIMS
_SAFE_USERINFO = _SUB_DELIMS + ":"
_SAFE_HOST = _SUB_DELIMS
#: The characters `percent_encode()` leaves as they are in a path.
SAFE_PATH = _SUB_DELIMS + ":@/"
_SAFE_PATH = SAFE_PATH
_SAFE_QUERY = _SUB_DELIMS + ":@/?"
_SAFE_FRAGMENT = _SAFE_QUERY


_PERCENT_ESCAPE = _re.compile("(%[0-9A-Fa-f]{2})")
_SCHEME_RE = _re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*")


def _lenient_utf8(text: str) -> bytes:
    """`text` as UTF-8 where a surrogate that `surrogateescape` cannot carry
    (a lone U+D800-U+DBFF or U+DC00-U+DC7F, which an NTFS name may hold) is
    written the way `surrogatepass` writes it, and an escaped byte
    (U+DC80-U+DCFF) is that byte again."""
    out = bytearray()
    for char in text:
        code = ord(char)
        if 0xDC80 <= code <= 0xDCFF:
            out.append(code - 0xDC00)
        else:
            out += char.encode("utf-8", "surrogatepass")
    return bytes(out)


def percent_encode(text: str, safe: str) -> str:
    """`text` percent-encoded as UTF-8, keeping the characters of `safe`.
    A decoded path may hold escaped bytes (`ERRORS`) and, from a Windows
    listing, a lone surrogate; neither may make the composer raise."""
    try:
        return _uritools.uriencode(text, safe, errors=ERRORS).decode()
    except UnicodeEncodeError:
        return _uritools.uriencode(_lenient_utf8(text), safe).decode()


_encode = percent_encode


def _encode_userinfo(userinfo: str) -> str:
    """A userinfo for composition: the user name escapes its colons, the
    password keeps them (RFC 3986 3.2.1)."""
    user, password = _split_userinfo_text(userinfo)
    text = _encode(user, _SAFE_USER)
    if password is not None:
        text += ":" + _encode(password, _SAFE_USERINFO)
    return text


def _encode_raw_query(query: str) -> str:
    """Emit a stored query for the wire: it is kept in its received,
    still-percent-encoded form (see `URI.query`), so an existing `%XX`
    escape and every delimiter (`&`, `=`, `+`, `;`) go out unchanged. Only
    characters that cannot appear in a query at all (a space, non-ASCII, a
    `%` that starts no escape) are encoded.

    Decoding at parse time and re-encoding here with `&`/`=`/`+` as safe
    characters turned `name=a%26b&sig=ab%2Bcd%3D%3D` into
    `name=a&b&sig=ab+cd==` on the wire, corrupting signed URLs."""
    pieces = _PERCENT_ESCAPE.split(query)
    for index in range(0, len(pieces), 2):
        if pieces[index]:
            pieces[index] = _encode(pieces[index], _SAFE_QUERY)
    return "".join(pieces)


def _compose_ipv6(address: _ip.IPv6Address) -> str:
    """A bracketed IPv6 literal; a zone is written after `%25` and
    percent-encoded (RFC 6874)."""
    text, sep, zone = address.compressed.partition("%")
    if sep:
        text = f"{text}%25{_encode(zone, '')}"
    return f"[{text}]"


def compose_host(host: "str | _IPAddress") -> str:
    """Encode a host for composition -- mirrors `uritools`' private
    `_authority()`/`_host()` composer helpers, including the fact that a
    bare (non-bracketed) string that happens to parse as IPv6 gets
    auto-bracketed (matches `uricompose`'s own behavior for a manually
    -constructed `Source(..., host="::1", ...)`, not just an
    already-bracketed literal). Deliberately NOT replaced by netimps'
    `join_host`/`FQDN`: those implement the RFC reading, this function the
    uritools one this module's output must round-trip through (and `FQDN`
    would reject names this composes), except where noted: an IPv6 zone is
    written as RFC 6874 says."""
    if isinstance(host, _ip.IPv6Address):
        return _compose_ipv6(host)
    if isinstance(host, _ip.IPv4Address):
        return host.compressed
    if host.startswith("[") and host.endswith("]"):
        return _compose_ipv6(_ipv6_from_literal(host[1:-1]))
    try:
        return _compose_ipv6(_ip.IPv6Address(host))
    except ValueError:
        pass
    host = host.lower()
    if not host.isascii():
        # RFC 3986 3.2.2: a non-ASCII registered name meant for DNS is produced in its
        # IDNA form (HTTP clients IDNA-encode only a non-ASCII host). A name the codec
        # rejects (an empty or over-long label, a surrogate-escaped byte) stays percent-encoded.
        try:
            return _idna_encode(host)
        except UnicodeError:
            pass
    return _encode(host, _SAFE_HOST)


_compose_host = compose_host


def _idna_encode(host: str) -> str:
    """`host` in IDNA (ASCII) form: IDNA 2008 with UTS #46 mapping through
    the `idna` package when installed (what `requests` itself uses), else
    the stdlib IDNA 2003 codec. Raises UnicodeError for an invalid name."""
    try:
        import idna as _idna
    except ImportError:
        return host.encode("idna").decode("ascii")
    # idna.IDNAError subclasses UnicodeError.
    return _idna.encode(host, uts46=True).decode("ascii")


def _port_text(port: "int | str") -> str:
    """The digits of a port that is 0-65535 (an int, or a `str` of digits);
    anything else is a `ValueError`, so a field that did not come from a
    parse cannot add a path or a second authority to the result."""
    if isinstance(port, str):
        if not port.isascii() or not port.isdigit():
            raise ValueError("invalid port: it must be digits")
        return str(_parse_port(port))
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("invalid port: it must be an integer")
    if not 0 <= port <= 65535:
        raise ValueError("port out of range 0-65535")
    return str(port)


def compose_uri(
    scheme: "str | None",
    userinfo: "str | None",
    host: "str | _IPAddress | None",
    port: "int | str | None",
    path: str,
    query: "str | None",
    fragment: "str | None",
) -> str:
    """The URI text of already-decoded components, percent-encoding each as
    its part of RFC 3986 asks. `None` leaves a component out; a path that
    cannot sit beside the authority given (or beside none) is a `ValueError`,
    as is an invalid scheme or port.

    This is direct string assembly, not `uritools.uricompose()`'s re-validation
    of every component (a scheme regex, authority re-parsing, IP-literal
    detection), which only matters for untrusted input. It reuses uritools'
    `uriencode()` and replicates only what changes the output string
    (lowercasing, IP-literal bracketing, the "./" escape of a colon in the first
    segment), and was checked against `uricompose()` on generated (scheme,
    userinfo, host, port, path, query, fragment) combinations."""
    parts = []
    if scheme is not None:
        if not _SCHEME_RE.fullmatch(scheme):
            raise ValueError("invalid scheme")
        parts.append(scheme)
        parts.append(":")
    has_authority = userinfo is not None or host is not None or port is not None
    if has_authority:
        parts.append("//")
        if userinfo is not None:
            parts.append(_encode_userinfo(userinfo))
            parts.append("@")
        if host is not None:
            parts.append(_compose_host(host))
        if port is not None:
            parts.append(":")
            parts.append(_port_text(port))
    path_enc = _encode(path, _SAFE_PATH) if path else ""
    if has_authority and path_enc and not path_enc.startswith("/"):
        raise ValueError("Invalid path with authority component")
    if not has_authority and path_enc.startswith("//"):
        raise ValueError("Invalid path without authority component")
    if scheme is None and not has_authority and not path_enc.startswith("/"):
        if ":" in path_enc.partition("/")[0]:
            path_enc = "./" + path_enc
    parts.append(path_enc)
    if query is not None:
        parts.append("?")
        parts.append(_encode_raw_query(query))
    if fragment is not None:
        parts.append("#")
        parts.append(_encode(fragment, _SAFE_FRAGMENT))
    return "".join(parts)


_compose_uri = compose_uri
