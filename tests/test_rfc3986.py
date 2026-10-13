"""The RFC 3986 split and percent-coding on the standard library: the
behaviours the URI layer relies on, one by one. `test_properties.py` holds the
same functions equal to `uritools` over generated text."""

from __future__ import annotations

import pytest

from uripath import URI, _rfc3986
from uripath.source import ERRORS, Source, percent_encode


def test_a_uri_splits_into_its_five_components():
    parts = _rfc3986.split("http://u:p@h:8080/a/b?x=1&y=2#frag")
    assert tuple(parts) == ("http", "u:p@h:8080", "/a/b", "x=1&y=2", "frag")
    assert parts.path == "/a/b" and parts.fragment == "frag"


def test_an_absent_component_is_none_and_an_empty_one_is_empty():
    assert tuple(_rfc3986.split("http://h/x")) == ("http", "h", "/x", None, None)
    assert tuple(_rfc3986.split("http://h/x?#")) == ("http", "h", "/x", "", "")
    assert tuple(_rfc3986.split("file:///x")) == ("file", "", "/x", None, None)
    assert tuple(_rfc3986.split("file:/x")) == ("file", None, "/x", None, None)


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("//h/x", (None, "h", "/x", None, None)),
        ("a/b:c", (None, None, "a/b:c", None, None)),
        ("c:/x", ("c", None, "/x", None, None)),
        ("1http://h/", (None, None, "1http://h/", None, None)),
        ("?q#f", (None, None, "", "q", "f")),
        ("", (None, None, "", None, None)),
        ("data:text/plain,a?b#c", ("data", None, "text/plain,a", "b", "c")),
    ],
)
def test_references_without_a_scheme_or_an_authority_split_as_rfc_3986_says(
    text, parts
):
    assert tuple(_rfc3986.split(text)) == parts


def test_a_fragment_ends_at_a_newline():
    assert _rfc3986.split("a#b\nc").fragment == "b"


def test_the_split_of_a_uri_is_what_its_parser_reads():
    assert Source.parse("http://u:p@h:8080").port == 8080
    assert URI("file:///x").source.host == ""
    assert URI("file:/x").source.host is None
    assert URI("http://h/a?b=1#c").query.to_pairs() == [("b", "1")]
    assert URI("http://h/a?b=1#c").fragment == "c"


@pytest.mark.parametrize(
    ("text", "decoded"),
    [
        ("a%20b", "a b"),
        ("%C3%A9", "\u00e9"),
        ("%c3%a9", "\u00e9"),
        ("%25", "%"),
        ("%2541", "%41"),
        ("100%", "100%"),
        ("%4", "%4"),
        ("%zz", "%zz"),
        ("%%41", "%A"),
        ("caf\u00e9%21", "caf\u00e9!"),
        ("[::1]%25en0", "[::1]%en0"),
        ("", ""),
    ],
)
def test_decode_replaces_each_valid_escape_and_keeps_the_rest(text, decoded):
    assert _rfc3986.decode(text) == decoded


def test_an_escape_that_is_not_utf_8_is_an_error_unless_it_is_escaped_through():
    with pytest.raises(UnicodeDecodeError):
        _rfc3986.decode("caf%E9.html")
    assert _rfc3986.decode("caf%E9.html", ERRORS) == "caf\udce9.html"
    assert _rfc3986.decode("caf%E9.html", "replace") == "caf\ufffd.html"


def test_decode_reads_the_escapes_in_the_encoding_given():
    assert _rfc3986.decode("caf%E9", "strict", "latin-1") == "caf\u00e9"


def test_text_that_the_encoding_cannot_hold_is_an_encode_error():
    with pytest.raises(UnicodeEncodeError):
        _rfc3986.decode("\u20ac%41", "strict", "latin-1")
    with pytest.raises(UnicodeEncodeError):
        _rfc3986.decode("\ud800", ERRORS)


def test_a_surrogate_escaped_byte_in_the_text_is_that_byte_again():
    # "%E2" then the escaped bytes of an euro sign tail: one character.
    assert _rfc3986.decode("%E2\udc82\udcac", ERRORS) == "\u20ac"


@pytest.mark.parametrize(
    ("text", "safe", "encoded"),
    [
        ("abcXYZ019-._~", "", "abcXYZ019-._~"),
        ("a b", "", "a%20b"),
        ("a/b", "", "a%2Fb"),
        ("a/b", "/", "a/b"),
        ("a=b&c", "=", "a=b%26c"),
        ("%", "", "%25"),
        ("caf\u00e9", "", "caf%C3%A9"),
        ("\u20ac", "", "%E2%82%AC"),
        ("a:b@c", "!$&'()*+,;=:@/", "a:b@c"),
        ("", "", ""),
    ],
)
def test_encode_escapes_what_is_neither_unreserved_nor_safe(text, safe, encoded):
    assert _rfc3986.encode(text, safe) == encoded


def test_encode_writes_the_hex_digits_in_upper_case():
    assert _rfc3986.encode("\u00ff\u00fe") == "%C3%BF%C3%BE"
    assert _rfc3986.encode(b"\xab\xcd") == "%AB%CD"


def test_encode_uses_bytes_as_they_are_and_text_in_the_encoding_given():
    assert _rfc3986.encode(b"caf\xe9 x") == "caf%E9%20x"
    assert _rfc3986.encode("caf\u00e9", encoding="latin-1") == "caf%E9"


def test_encode_raises_for_text_the_encoding_cannot_hold_unless_told_otherwise():
    with pytest.raises(UnicodeEncodeError):
        _rfc3986.encode("\udc80")
    assert _rfc3986.encode("a\udc80", errors=ERRORS) == "a%80"
    assert _rfc3986.encode("a\u20ac", encoding="ascii", errors="ignore") == "a"


def test_percent_encode_writes_a_lone_surrogate_the_way_surrogatepass_does():
    assert percent_encode("a\ud800b", "") == "a%ED%A0%80b"
    assert percent_encode("a\udc80b", "") == "a%80b"


def test_a_path_round_trips_through_its_text():
    for path in ("/a b/\u00e9/%41", "/caf\udce9", "/x?y#z"):
        uri = URI("http://h").with_path(path)
        assert URI(uri.as_uri()).path == path
