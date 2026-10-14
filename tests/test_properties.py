"""Property-based tests (hypothesis) for URI parsing/joining and parity
with `pathlib.PurePosixPath` on the operations that are supposed to behave
identically (see `docs/divergences.md` for the ones that deliberately
don't -- those are out of scope here, not asserted against).
"""

from __future__ import annotations

import ipaddress
import pathlib
import sys

import pytest

uritools = pytest.importorskip("uritools")
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from uripath import URI, Query, _rfc3986
from uripath.source import ERRORS, Source, fold_host, percent_encode
from uripath.source._compose import _compose_uri, _lenient_utf8
from uripath.source._parse import (
    _decode_host,
    _remove_dot_segments,
    _split_authority,
)

# A "safe" path segment: letters/digits/-/_ only, never empty, never "."
# or ".." -- keeps every property below unambiguous without wading into
# the documented "we never resolve .." / dot-collapsing divergences.
segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="-_"
    ),
    min_size=1,
    max_size=12,
).filter(lambda s: s not in (".", ".."))

segments_list = st.lists(segment, min_size=0, max_size=6)
nonempty_segments_list = st.lists(segment, min_size=1, max_size=6)


def _posix(segs: list[str]) -> str:
    """Absolute posix path string for a list of segments."""
    return "/" + "/".join(segs)


# --- Parse/Format identity ---


@given(segs=segments_list)
@settings(max_examples=200)
def test_uri_str_roundtrip(segs):
    u = URI(_posix(segs))
    assert URI(str(u)) == u


@given(segs=segments_list)
@settings(max_examples=200)
def test_uri_as_uri_roundtrip(segs):
    u = URI(_posix(segs))
    assert URI(u.as_uri()) == u


# --- Path joining ---


@given(base=segments_list, a=segment, b=segment)
@settings(max_examples=200)
def test_join_is_associative(base, a, b):
    u = URI(_posix(base))
    assert (u / a) / b == u.joinpath(a, b)


@given(base=segments_list, tail=nonempty_segments_list)
@settings(max_examples=200)
def test_joinpath_matches_repeated_truediv(base, tail):
    u = URI(_posix(base))
    joined = u.joinpath(*tail)
    stepped = u
    for part in tail:
        stepped = stepped / part
    assert joined == stepped


# --- Parity vs pathlib.PurePosixPath ---


@given(segs=nonempty_segments_list)
@settings(max_examples=200)
def test_segments_match_pure_posix_path_parts(segs):
    path_str = _posix(segs)
    u = URI(path_str)
    pp = pathlib.PurePosixPath(path_str)
    # URI.segments keeps a leading "" to mark the root ("/a/b" -> ("", "a",
    # "b")); PurePosixPath.parts marks it as "/" instead ("/a/b" -> ("/",
    # "a", "b")). Everything after that first element matches exactly.
    assert u.segments[0] == ""
    assert u.segments[1:] == pp.parts[1:]


@given(segs=nonempty_segments_list)
@settings(max_examples=200)
def test_name_matches_pure_posix_path(segs):
    path_str = _posix(segs)
    assert URI(path_str).name == pathlib.PurePosixPath(path_str).name


@given(common=segments_list, tail=nonempty_segments_list)
@settings(max_examples=200)
def test_relative_to_matches_pure_posix_path(common, tail):
    child_segs = common + tail
    child_str = _posix(child_segs)
    base_str = _posix(common)

    u_child, u_base = URI(child_str), URI(base_str)
    pp_child, pp_base = pathlib.PurePosixPath(child_str), pathlib.PurePosixPath(
        base_str
    )

    u_rel = u_child.relative_to(u_base)
    pp_rel = pp_child.relative_to(pp_base)
    assert u_rel.segments == pp_rel.parts


@given(a=nonempty_segments_list, b=nonempty_segments_list)
@settings(max_examples=200)
def test_relative_to_unrelated_raises_on_both(a, b):
    # Force genuinely unrelated paths (b must not start with a, and vice
    # versa) by prefixing each with a distinct marker segment.
    a_str = _posix(["left-marker"] + a)
    b_str = _posix(["right-marker"] + b)

    u_raises = False
    try:
        URI(a_str).relative_to(URI(b_str))
    except ValueError:
        u_raises = True

    pp_raises = False
    try:
        pathlib.PurePosixPath(a_str).relative_to(pathlib.PurePosixPath(b_str))
    except ValueError:
        pp_raises = True

    assert u_raises == pp_raises == True


@given(segs=nonempty_segments_list)
@settings(max_examples=200)
def test_match_trailing_segment_wildcard_matches_pure_posix_path(segs):
    path_str = _posix(segs)
    pattern = "*" + segs[-1][1:] if len(segs[-1]) > 1 else "*"
    assert URI(path_str).match(pattern) == pathlib.PurePosixPath(path_str).match(
        pattern
    )


@given(segs=nonempty_segments_list)
@settings(max_examples=200)
def test_is_relative_to_matches_pure_posix_path(segs):
    path_str = _posix(segs)
    parent_str = _posix(segs[:-1])
    u, pp = URI(path_str), pathlib.PurePosixPath(path_str)
    u_parent, pp_parent = URI(parent_str), pathlib.PurePosixPath(parent_str)
    assert u.is_relative_to(u_parent) == pp.is_relative_to(pp_parent) == True
    # The str form agrees with the object form: `other` is not anchored at
    # self's root, which would answer False for every *relative* self.
    assert u.is_relative_to(parent_str) == pp.is_relative_to(parent_str) == True


@given(segs=nonempty_segments_list)
@settings(max_examples=200)
def test_is_relative_to_str_matches_pure_posix_path_for_unrelated_other(segs):
    # The negative direction of the same oracle: a str `other` that is not a
    # prefix must answer False for both, relative and absolute self alike.
    other_str = _posix(["zzz-unrelated"])
    for path_str in (_posix(segs), "/" + _posix(segs)):
        u, pp = URI(path_str), pathlib.PurePosixPath(path_str)
        assert u.is_relative_to(other_str) == pp.is_relative_to(other_str)


# --- Generic Pathname (URI, MemPath) vs PurePosixPath: match, parents,
# MemPath normalization. Small alphabets so wildcards actually hit. ---

_match_name = st.sampled_from(["a", "b", "ab", "a.py", ".a", "b.a"])
_match_pattern_part = st.sampled_from(
    ["a", "b", "*", "?", "a*", "*.py", "[ab]", "[!a]*", "**", ".*", "."]
)


def _generic_classes():
    from pathapi.mempath import MemPath

    return (URI, MemPath)


@given(
    rooted=st.booleans(),
    names=st.lists(_match_name, min_size=0, max_size=4),
    pattern_rooted=st.booleans(),
    pattern_parts=st.lists(_match_pattern_part, min_size=0, max_size=4),
    case_sensitive=st.sampled_from([None, True, False]),
)
@settings(max_examples=400)
def test_generic_match_matches_pure_posix_path(
    rooted, names, pattern_rooted, pattern_parts, case_sensitive
):
    """Multi-segment and rooted patterns (not just a trailing "*"): right
    anchoring, `*` never crossing "/", anchors, and the empty pattern."""
    path_str = ("/" if rooted else "") + "/".join(names)
    pattern = ("/" if pattern_rooted else "") + "/".join(pattern_parts)
    kwargs = {} if case_sensitive is None else {"case_sensitive": case_sensitive}

    def outcome(p):
        try:
            if isinstance(p, pathlib.PurePath) and sys.version_info < (3, 12):
                # 3.9-3.11 stdlib has no case_sensitive=; posix is sensitive.
                if case_sensitive is False:
                    return pathlib.PurePosixPath(str(p).lower()).match(pattern.lower())
                return p.match(pattern)
            return p.match(pattern, **kwargs)
        except ValueError:
            return ValueError

    expected = outcome(pathlib.PurePosixPath(path_str))
    for cls in _generic_classes():
        assert outcome(cls(path_str)) == expected, (cls, path_str, pattern)


@given(rooted=st.booleans(), segs=segments_list)
@settings(max_examples=200)
def test_generic_parents_and_parent_match_pure_posix_path(rooted, segs):
    path_str = ("/" if rooted else "") + "/".join(segs)
    pp = pathlib.PurePosixPath(path_str)

    def spell(p):
        s = p.as_posix()
        return "" if s == "." else s

    for cls in _generic_classes():
        p = cls(path_str)
        assert [spell(x) for x in p.parents] == [spell(x) for x in pp.parents]
        assert spell(p.parent) == spell(pp.parent)
        for ancestor in pp.parents:
            assert p.is_relative_to(spell(ancestor)) is True


_mem_piece = st.sampled_from(["", ".", "a", "b", "cd"])


# --- uritools oracle: the standard-library split, decoding and encoding ---
# `URI._parse_uri`/`URI._format_parsed_parts` split, decode and compose with
# `uripath._rfc3986` and string assembly, and must stay equal to what the
# `uritools` accessors and `uricompose()` return. uritools is a development
# dependency for this purpose only: it is the oracle, and a mismatch means the
# code is wrong, not these tests.

_scheme_st = st.one_of(
    st.none(), st.from_regex(r"[a-zA-Z][a-zA-Z0-9+.-]{0,8}", fullmatch=True)
)
_userinfo_st = st.one_of(
    st.none(), st.text(alphabet="abcXYZ012:%40@!$&'()*+,;=~-._", max_size=12)
)
_host_st = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet="abcXYZ012.-%~", max_size=15),
    st.just("[::1]"),
    st.just("[2001:db8::1]"),
    st.just("[::1"),  # malformed bracket -- must raise on both sides
    st.text(alphabet="0123456789", max_size=6),  # pure-digit host (uritools quirk)
)
_port_st = st.one_of(st.none(), st.integers(min_value=0, max_value=99999).map(str))
_path_st = st.text(alphabet="abcXYZ012/.%20~!$&'()*+,;=:@-_", max_size=25)
_query_st = st.one_of(st.none(), st.text(alphabet="abcXYZ012=&%20+", max_size=15))
_frag_st = st.one_of(st.none(), st.text(alphabet="abcXYZ012%20-_", max_size=10))


@st.composite
def _uri_string(draw):
    scheme = draw(_scheme_st)
    userinfo = draw(_userinfo_st)
    host = draw(_host_st)
    port = draw(_port_st)
    path = draw(_path_st)
    query = draw(_query_st)
    frag = draw(_frag_st)

    parts = []
    if scheme is not None:
        parts.append(scheme + ":")
    has_authority = host is not None
    if has_authority:
        parts.append("//")
        if userinfo is not None:
            parts.append(userinfo + "@")
        parts.append(host)
        if port is not None:
            parts.append(":" + port)
    if path:
        if has_authority and not path.startswith("/"):
            path = "/" + path
        parts.append(path)
    if query is not None:
        parts.append("?" + query)
    if frag is not None:
        parts.append("#" + frag)
    return "".join(parts)


# The oracle is uritools' getters, with these deliberate contract changes:
# * the query is the RAW, still-encoded component, never decoded at parse;
# * percent-escapes that are not UTF-8 decode with surrogateescape instead
#   of raising UnicodeDecodeError;
# * a data: path skips dot-segment removal (RFC 2397 payloads are opaque);
# * the authority differs from uritools in three ways, all applied by
#   `_oracle_authority` and nowhere else:
#   - a host of ASCII digits alone (no ':' after it) is the host, as
#     RFC 3986 3.2.2 has it; uritools reads it as a port and returns '';
#   - a port above 65535 is a ValueError (RFC 3986 3.2.3 leaves the range
#     open, TCP does not); uritools accepts any number of digits;
#   - a ':' followed by anything but digits, after a name that is not a
#     bracketed address, is an invalid port (ValueError); uritools makes the
#     whole `h:abc` the host name.
_ERRORS = "surrogateescape"


def _kind(error: Exception) -> str:
    """The name of the builtin an error is: uritools raises `ValueError`, the
    parser a subclass of it."""
    return "ValueError" if isinstance(error, ValueError) else type(error).__name__


def _oracle_authority(uri: str, parsed):
    """`(host, port)` of uritools, with the documented differences, and a host of
    `None` for no authority where uritools has none for both."""
    authority = parsed.authority
    hostinfo = "" if authority is None else authority.rpartition("@")[2]
    _, colon, tail = hostinfo.rpartition(":")
    if colon and tail.lstrip("0123456789") and not hostinfo.startswith("["):
        raise ValueError("invalid port: it must be digits")
    host, port = parsed.gethost(errors=_ERRORS) or "", parsed.getport()
    if authority is None:
        host = None
    if hostinfo and ":" not in hostinfo and hostinfo.isascii() and hostinfo.isdigit():
        host = hostinfo
    if port is not None and port > 65535:
        raise ValueError("port out of range 0-65535")
    return host, port


def _oracle_parse(uri: str):
    parsed = uritools.urisplit(uri)
    scheme = parsed.getscheme()
    if scheme == "data":
        path = uritools.uridecode(parsed.path, errors=_ERRORS)
    else:
        path = parsed.getpath(errors=_ERRORS)
    host, port = _oracle_authority(uri, parsed)
    return (
        scheme,
        parsed.getuserinfo(errors=_ERRORS),
        host,
        port,
        path,
        parsed.query or "",
        parsed.getfragment(errors=_ERRORS) or "",
    )


def _fast_parse(uri: str):
    scheme, authority, path, query, fragment = _rfc3986.split(uri)
    scheme = scheme.lower() if scheme is not None else None
    userinfo, host, port = _split_authority(authority)
    if userinfo is not None:
        userinfo = _rfc3986.decode(userinfo, _ERRORS)
    host = _decode_host(host) if host is not None else None
    if scheme != "data":
        path = _remove_dot_segments(path)
    path = _rfc3986.decode(path, _ERRORS)
    fragment = _rfc3986.decode(fragment, _ERRORS) if fragment is not None else None
    return scheme, userinfo, host, port, path, (query or ""), (fragment or "")


def _folded(parsed):
    """`parsed` with its host in lower case: uritools folds a host name, and
    this parser keeps the spelling it was given (pinned in test_host_case.py)."""
    if parsed[0] == "EXC":
        return parsed
    return (*parsed[:2], fold_host(parsed[2]), *parsed[3:])


@given(uri=_uri_string())
@settings(max_examples=1000)
def test_fast_parse_matches_uritools_getters(uri):
    try:
        fast = _fast_parse(uri)
    except Exception as e:
        fast = ("EXC", _kind(e))
    try:
        oracle = _oracle_parse(uri)
    except Exception as e:
        oracle = ("EXC", type(e).__name__)
    assert _folded(fast) == oracle, f"uri={uri!r}"


@given(uri=_uri_string())
@settings(max_examples=500)
def test_uri_parse_uri_matches_oracle_components(uri):
    """Same oracle check, but through the real `URI._parse_uri` (not just
    the standalone helper functions), so a future refactor that changes
    how they're wired together is still caught."""
    try:
        source, path, query, fragment = URI._parse_uri(uri)
        fast = (
            source.scheme,
            source.userinfo,
            source.host,
            source.port,
            path,
            str(query),
            fragment,
        )
    except Exception as e:
        fast = ("EXC", _kind(e))
    try:
        oracle = _oracle_parse(uri)
    except Exception as e:
        oracle = ("EXC", type(e).__name__)
    assert _folded(fast) == oracle, f"uri={uri!r}"


_compose_scheme_st = st.one_of(st.none(), st.just(""), _scheme_st)
_compose_userinfo_st = st.one_of(st.none(), st.just(""), _userinfo_st)
_compose_host_st = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet="abcXYZ012.-%~!$&'()*+,;=", max_size=15),
    st.builds(lambda: ipaddress.IPv6Address("::1")),
    st.builds(lambda: ipaddress.IPv6Address("2001:db8::1")),
    st.builds(lambda: ipaddress.IPv4Address("192.168.1.1")),
    st.just("[::1]"),
    st.just("::1"),
)
_compose_port_st = st.one_of(st.none(), st.integers(min_value=0, max_value=99999))
_compose_query_st = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet="abcXYZ012=&%20+!$&'()*+,;=:@/?~", max_size=20),
)
_compose_frag_st = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet="abcXYZ012%20-_!$&'()*+,;=:@/?~", max_size=15),
)


_HEX = "0123456789abcdefABCDEF"


def _oracle_raw_query(query: str) -> str:
    """A stored query is already encoded, so composing keeps every
    valid %XX escape and every delimiter, and encodes only characters that
    cannot appear in a query (uritools.uricompose encodes "%" itself, which
    double-encoded a received query)."""
    out = []
    index = 0
    while index < len(query):
        char = query[index]
        escape = query[index + 1 : index + 3]
        if char == "%" and len(escape) == 2 and all(h in _HEX for h in escape):
            out.append(query[index : index + 3])
            index += 3
            continue
        out.append(uritools.uriencode(char, "!$&'()*+,;=:@/?").decode())
        index += 1
    return "".join(out)


def _with_raw_query(uri: str, query) -> str:
    if query is None:
        return uri
    head, sep, fragment = uri.partition("#")
    return f"{head}?{_oracle_raw_query(query)}{sep}{fragment}"


def _oracle_format_parsed_parts(source, path, query, fragment, sanitize=True):
    parts = {"path": path}
    if fragment:
        parts["fragment"] = fragment
    source_ = source._asdict()
    if sanitize:
        source_["userinfo"] = (source_["userinfo"] or "").split(":", maxsplit=1)[0]
    parts.update(source_)
    # Documented differences from uricompose: a port of 0 is kept (it is a
    # valid port and part of the endpoint's identity), and a port above
    # 65535 is a ValueError.
    if (parts.get("port") or 0) > 65535:
        raise ValueError("port out of range 0-65535")
    # An empty host is an empty authority, which uricompose writes as "//".
    kept = {
        k: v
        for k, v in parts.items()
        if v or (k == "port" and v == 0) or (k == "host" and v == "")
    }
    return _with_raw_query(uritools.uricompose(**kept), query or None)


@given(
    scheme=_compose_scheme_st,
    userinfo=_compose_userinfo_st,
    host=_compose_host_st,
    port=_compose_port_st,
    path=_path_st,
    query=_compose_query_st,
    fragment=_compose_frag_st,
    sanitize=st.booleans(),
)
@settings(max_examples=1000)
def test_uri_format_parsed_parts_matches_uricompose(
    scheme, userinfo, host, port, path, query, fragment, sanitize
):
    source = Source(scheme, userinfo, host, port)
    try:
        # uricompose folds a host name and the composer keeps its spelling: the
        # two texts differ in the case of the host and nowhere else.
        spelled = URI._format_parsed_parts(
            source, path, query, fragment, sanitize=sanitize
        )
        fast = URI._format_parsed_parts(
            source._replace(host=fold_host(host)),
            path,
            query,
            fragment,
            sanitize=sanitize,
        )
        assert spelled.lower() == fast.lower()
    except AssertionError:
        raise
    except Exception as e:
        fast = ("EXC", _kind(e))
    try:
        oracle = _oracle_format_parsed_parts(source, path, query, fragment, sanitize)
    except Exception as e:
        oracle = ("EXC", type(e).__name__)
    assert (
        fast == oracle
    ), f"source={source!r} path={path!r} query={query!r} fragment={fragment!r} sanitize={sanitize}"


@given(
    # `_compose_uri` is a low-level primitive: it expects an
    # already-lowercased scheme (its callers -- `_format_parsed_parts`,
    # `DAVURIPath._wire_uri` -- do the lowering themselves before calling it,
    # matching how it's actually used in production), so this doesn't
    # generate uppercase schemes -- that's `_format_parsed_parts`'s
    # contract, already covered by the test above.
    scheme=st.one_of(st.none(), st.just("http"), st.just("https")),
    userinfo=_compose_userinfo_st,
    host=_compose_host_st,
    port=_compose_port_st,
    path=_path_st,
    query=_compose_query_st,
    fragment=_compose_frag_st,
)
@settings(max_examples=300)
def test_compose_uri_matches_uricompose_direct(
    scheme, userinfo, host, port, path, query, fragment
):
    """`_compose_uri` used directly (not via the truthy-filtering
    `_format_parsed_parts` wrapper) -- this is DAVURIPath._wire_uri()'s call
    shape: None-checked, not truthy-filtered."""
    try:
        # uricompose folds a host name and the composer keeps its spelling: the
        # two texts differ in the case of the host and nowhere else.
        spelled = _compose_uri(
            scheme, userinfo, host, port, path, query or None, fragment or None
        )
        fast = _compose_uri(
            scheme,
            userinfo,
            fold_host(host),
            port,
            path,
            query or None,
            fragment or None,
        )
        assert spelled.lower() == fast.lower()
    except AssertionError:
        raise
    except Exception as e:
        fast = ("EXC", _kind(e))
    try:
        if (port or 0) > 65535:  # the documented difference, see above
            raise ValueError("port out of range 0-65535")
        oracle = _with_raw_query(
            uritools.uricompose(
                scheme=scheme,
                userinfo=userinfo,
                host=host,
                port=port,
                path=path,
                fragment=fragment or None,
            ),
            query or None,
        )
    except Exception as e:
        oracle = ("EXC", type(e).__name__)
    assert (
        fast == oracle
    ), f"scheme={scheme!r} userinfo={userinfo!r} host={host!r} port={port!r}"


# --- Names that URI syntax gives a meaning to ---------------------------------
#
# The properties above draw segments from letters, digits, "-" and "_". These
# draw any text a POSIX file name may hold, and a set biased towards "?", "#",
# "%", ":", space, "\", "[" and non-ASCII letters.

BACKSLASH = chr(92)
_any_name = st.text(
    alphabet=st.characters(blacklist_characters="/\x00", blacklist_categories=("Cs",)),
    min_size=1,
    max_size=10,
).filter(lambda s: s not in (".", ".."))
_spicy_name = st.text(
    alphabet="ab?#%20: @[]" + BACKSLASH + "+&=;~é.", min_size=1, max_size=8
).filter(lambda s: s not in (".", ".."))
_name = st.one_of(_any_name, _spicy_name)


@given(name=_name)
@settings(max_examples=300)
def test_a_joined_child_keeps_the_name_it_was_given(name):
    base = URI("sftp://host/dir")
    child = base / name
    assert child.name == name
    assert child.path == "/dir/" + name
    assert child.parent == base


@given(name=_name)
@settings(max_examples=300)
def test_a_joined_child_survives_its_own_uri_text(name):
    child = URI("sftp://host/dir") / name
    assert URI(child.as_uri()) == child
    assert URI(str(child)) == child


_pairs = st.lists(
    st.tuples(
        st.text(alphabet="ab=&;%+ #?\u00e9/", min_size=1, max_size=5),
        st.one_of(st.none(), st.text(alphabet="ab=&;%+ #?\u00e9/", max_size=5)),
    ),
    max_size=4,
)


@given(pairs=_pairs)
@settings(max_examples=300)
def test_query_pairs_survive_a_uri_round_trip(pairs):
    from uripath import Query

    assert Query(pairs).to_pairs() == [(k, v) for k, v in pairs]
    assert Query.parse(str(Query(pairs))) == Query(pairs)
    if pairs:
        uri = URI("http://host/p").with_query(Query(pairs))
        assert URI(uri.as_uri()).query.to_pairs() == [(k, v) for k, v in pairs]


_userinfo = st.one_of(
    st.none(), st.text(alphabet="abU:@/?#%" + chr(233) + " ", min_size=1, max_size=8)
)
_host = st.text(alphabet="abc.-", min_size=1, max_size=8).filter(
    lambda h: not h.startswith((".", "-"))
)


@given(
    userinfo=_userinfo,
    host=_host,
    port=st.one_of(st.none(), st.integers(min_value=1, max_value=65535)),
)
@settings(max_examples=300)
def test_a_source_survives_its_unsanitized_text(userinfo, host, port):
    source = Source("sftp", userinfo, host, port)
    assert Source.parse(source.reveal()) == source


@given(
    user=st.text(alphabet="abU", min_size=1, max_size=4),
    password=st.text(alphabet="xyz%@/#" + chr(233), min_size=3, max_size=8),
    host=_host,
)
@settings(max_examples=300)
def test_a_password_in_the_userinfo_is_not_in_the_text_a_log_would_show(
    user, password, host
):
    source = Source("sftp", f"{user}:{password}", host, None)
    assert password not in repr(source)
    assert password not in str(source)
    assert password not in str(URI(source.reveal() + "/x"))


# --- uritools oracle: the functions of uripath._rfc3986 ---------------------
#
# Each property compares an outcome: the value, or the name of the exception
# that was raised. The differences from uritools that are deliberate are the
# tests at the end of this section, each with its reason.

#: Lone surrogates of the three kinds the code meets: the escaped bytes of
#: `surrogateescape` (DC80-DCFF), the ones it cannot carry (DC00-DC7F) and a
#: high surrogate, which a Windows file name may hold.
_SURROGATES = ["\ud800", "\udbff", "\udc00", "\udc7f", "\udc80", "\udcff"]

_text_pieces = st.one_of(
    st.sampled_from(list("ab%:/?#@[]=&+ .~-_AF09\n")),
    st.sampled_from(
        ["%41", "%e9", "%C3%A9", "%zz", "%4", "%", "%%41", "\u00e9", "\u20ac"]
    ),
    st.sampled_from(_SURROGATES),
    st.characters(max_codepoint=0x2FFF, exclude_categories=("Cs",)),
)
_any_text = st.lists(_text_pieces, max_size=12).map("".join)
_error_handlers = st.sampled_from(["strict", "surrogateescape", "replace", "ignore"])
_encodings = st.sampled_from(["utf-8", "latin-1", "ascii", "utf-16"])


def _outcome(call):
    try:
        return ("value", call())
    except Exception as error:  # noqa: BLE001 - the type is what is compared
        return ("error", type(error).__name__)


@given(text=_any_text)
@settings(max_examples=1000)
def test_split_matches_urisplit(text):
    assert tuple(_rfc3986.split(text)) == tuple(uritools.urisplit(text))


@given(uri=_uri_string())
@settings(max_examples=500)
def test_split_matches_urisplit_on_generated_uris(uri):
    ours, theirs = _rfc3986.split(uri), uritools.urisplit(uri)
    assert tuple(ours) == tuple(theirs)
    assert (ours.scheme, ours.authority, ours.path, ours.query, ours.fragment) == (
        theirs.scheme,
        theirs.authority,
        theirs.path,
        theirs.query,
        theirs.fragment,
    )


@given(text=_any_text, errors=_error_handlers, encoding=_encodings)
@settings(max_examples=1500)
def test_decode_matches_uridecode(text, errors, encoding):
    assert _outcome(lambda: _rfc3986.decode(text, errors, encoding)) == _outcome(
        lambda: uritools.uridecode(text, encoding, errors)
    )


@given(text=_any_text)
@settings(max_examples=500)
def test_decode_defaults_match_uridecode(text):
    assert _outcome(lambda: _rfc3986.decode(text)) == _outcome(
        lambda: uritools.uridecode(text)
    )


_safe_sets = st.one_of(
    st.just(""),
    st.just("/"),
    st.just("!$&'()*+,;=:@/"),
    st.just("!$&'()*+,;=:@/?"),
    st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=8),
)
_encode_data = st.one_of(
    _any_text,
    st.binary(max_size=12),
    st.lists(_text_pieces, max_size=6).map(
        lambda p: "".join(p).encode("utf-8", "surrogatepass")
    ),
)


@given(data=_encode_data, safe=_safe_sets, errors=_error_handlers, encoding=_encodings)
@settings(max_examples=1500)
def test_encode_matches_uriencode(data, safe, errors, encoding):
    def ours():
        return _rfc3986.encode(data, safe, encoding=encoding, errors=errors)

    def theirs():
        return uritools.uriencode(data, safe, encoding, errors).decode()

    assert _outcome(ours) == _outcome(theirs)


@given(data=_encode_data)
@settings(max_examples=300)
def test_encode_defaults_match_uriencode(data):
    assert _outcome(lambda: _rfc3986.encode(data)) == _outcome(
        lambda: uritools.uriencode(data).decode()
    )


@given(text=_any_text, safe=_safe_sets)
@settings(max_examples=1000)
def test_percent_encode_matches_uriencode_with_the_fallback_for_lone_surrogates(
    text, safe
):
    def oracle():
        try:
            return uritools.uriencode(text, safe, errors=ERRORS).decode()
        except UnicodeEncodeError:
            return uritools.uriencode(_lenient_utf8(text), safe).decode()

    assert _outcome(lambda: percent_encode(text, safe)) == _outcome(oracle)


def test_encode_ignores_a_safe_character_that_is_not_ascii_where_uriencode_raises():
    # `urllib.parse.quote_from_bytes` drops a non-ASCII character of `safe`;
    # uritools encodes `safe` as ASCII and raises. Every safe set in this
    # package is a constant of ASCII characters.
    assert _rfc3986.encode("a b", "\u00e9") == "a%20b"
    with pytest.raises(UnicodeEncodeError):
        uritools.uriencode("a b", "\u00e9")


def test_decode_takes_text_where_uridecode_also_takes_bytes():
    # Every caller decodes the `str` component of a URI. `uridecode` of bytes
    # gives bytes (or text for an encoding); nothing here needs that.
    with pytest.raises(TypeError):
        _rfc3986.decode(b"a%41")


_term_pieces = st.sampled_from(list("ab%+ ;&=#?/\u00e9") + ["%41", "%26", "%3D", "%e9"])
_term_text = st.lists(_term_pieces, max_size=6).map("".join)
_query_pair_values = st.one_of(
    st.none(), _term_text, st.binary(max_size=4), st.integers(0, 99)
)
_query_pairs_st = st.lists(st.tuples(_term_text, _query_pair_values), max_size=5)


def _oracle_querylist(items, sep, encoding):
    """What `Query(pairs)` was made of when it called uritools: every name and
    value escapes the separator, "=" and "+" besides what a query escapes."""
    safe = "!$&'()*+,;=:@/?".replace(sep, "").replace("=", "").replace("+", "")
    terms = []
    for key, value in items:
        name = uritools.uriencode(key, safe, encoding)
        if value is None:
            terms.append(name)
        elif isinstance(value, (bytes, str)):
            terms.append(name + b"=" + uritools.uriencode(value, safe, encoding))
        else:
            terms.append(name + b"=" + uritools.uriencode(str(value), safe, encoding))
    return sep.encode("ascii").join(terms).decode()


@given(
    pairs=_query_pairs_st,
    separator=st.sampled_from(["&", ";", "|"]),
    encoding=st.sampled_from(["utf-8", "latin-1"]),
)
@settings(max_examples=600)
def test_a_query_built_from_pairs_is_the_text_uritools_encodes(
    pairs, separator, encoding
):
    assert _outcome(
        lambda: str(Query(pairs, separator=separator, encoding=encoding))
    ) == _outcome(lambda: _oracle_querylist(pairs, separator, encoding))


@given(
    pairs=st.dictionaries(
        _term_text, st.one_of(_term_text, st.lists(_term_text, max_size=3)), max_size=4
    )
)
@settings(max_examples=300)
def test_a_query_built_from_a_mapping_is_the_text_uritools_encodes(pairs):
    items = []
    for key, value in pairs.items():
        if isinstance(value, list):
            items.extend((key, v) for v in value)
        else:
            items.append((key, value))
    assert str(Query(pairs)) == _oracle_querylist(items, "&", "utf-8")


@given(text=_any_text, encoding=st.sampled_from(["utf-8", "latin-1"]))
@settings(max_examples=800)
def test_the_pairs_of_query_text_are_the_terms_uritools_decodes(text, encoding):
    def oracle():
        found = []
        for term in text.split("&"):
            if not term:
                continue
            name, equals, value = term.partition("=")
            found.append(
                (
                    uritools.uridecode(name, encoding, ERRORS),
                    uritools.uridecode(value, encoding, ERRORS) if equals else None,
                )
            )
        return found

    assert _outcome(
        lambda: Query.parse(text, encoding=encoding).to_pairs()
    ) == _outcome(oracle)
