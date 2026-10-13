import copy
import pickle

import pytest

from uripath import URI
from uripath.query import Query


def test_from_text_keeps_the_text_and_decodes_the_pairs():
    q = Query.parse("a=1&b=2")
    assert str(q) == "a=1&b=2"
    assert q.to_dict() == {"a": ["1"], "b": ["2"]}


def test_from_dict_single_values():
    q = Query({"a": "1", "b": "2"})
    assert set(str(q).split("&")) == {"a=1", "b=2"}


def test_from_dict_list_values_repeats_key():
    # The example of tests/test_smoke.py: a sequence value repeats the name.
    q = Query({"test": "://$#!1", "test2&": [1, 2]})
    d = q.to_dict()
    assert d["test"] == ["://$#!1"]
    assert d["test2&"] == ["1", "2"]


def test_pairs_come_from_a_named_method_in_order():
    q = Query({"a": "1", "b": ["2", "3"]})
    assert q.to_pairs() == [("a", "1"), ("b", "2"), ("b", "3")]
    assert Query.parse("flag&k=v&k=w").to_pairs() == [
        ("flag", None),
        ("k", "v"),
        ("k", "w"),
    ]


def test_special_characters_encoded_and_decoded():
    q = Query({"key": "a b/c?d#e&f"})
    # round-trip through the encoded string form
    decoded = Query.parse(str(q)).to_dict()
    assert decoded["key"] == ["a b/c?d#e&f"]


def test_none_value_emits_bare_key():
    q = Query([("flag", None)])
    assert str(q) == "flag"


def test_custom_separator():
    q = Query({"a": "1", "b": "2"}, separator=";")
    assert ";" in str(q)
    assert "&" not in str(q)
    assert q.separator == ";"


def test_a_plus_in_a_mapping_is_escaped_so_it_cannot_read_as_a_space():
    query = Query({"sig": "ab+cd=="})
    assert str(query) == "sig=ab%2Bcd%3D%3D"
    assert query.to_pairs() == [("sig", "ab+cd==")]
    offset = Query({"since": "2026-10-07T00:00:00+00:00"})
    assert "+" not in str(offset)
    assert offset.to_dict() == {"since": ["2026-10-07T00:00:00+00:00"]}
    assert str(Query({"a+b": "c"})) == "a%2Bb=c"
    assert str(Query([("a+b", "c+d")])) == "a%2Bb=c%2Bd"


def test_what_the_encoder_wrote_decodes_to_what_it_was_given():
    values = [
        "+",
        "=",
        "&",
        "#",
        "%",
        " ",
        ";",
        "a+b c",
        "100%+1",
        "ü+中",
        "?/:@",
    ]
    for value in values:
        for query in (Query({"k": value}), Query([("k", value)])):
            assert query.to_pairs() == [("k", value)], value
            assert Query.parse(str(query)).to_pairs() == [("k", value)], value
    name = Query({"a=b+c&d": "x"})
    assert name.to_pairs() == [("a=b+c&d", "x")]


def test_a_query_built_from_text_is_kept_byte_for_byte():
    for text in ("a+b=c+d", "a=1&b=%2B&c=%zz", "x=a b", "sig=ab%2Bcd%3D%3D"):
        assert str(Query.parse(text)) == text
    assert Query.parse("a+b=c+d").to_pairs() == [("a+b", "c+d")]
    assert Query.parse("sig=ab%2Bcd%3D%3D").to_pairs() == [("sig", "ab+cd==")]


def test_decoding_reads_a_plus_as_a_plus_not_as_a_space():
    # RFC 3986, not form-urlencoded: only %XX escapes are decoded.
    assert Query.parse("q=a+b&r=a%20b").to_pairs() == [("q", "a+b"), ("r", "a b")]


def test_an_escape_that_is_not_utf8_survives_instead_of_raising():
    query = Query.parse("a=%E9&%FF=b")
    assert query.to_pairs() == [("a", "\udce9"), ("\udcff", "b")]
    assert query == Query.parse("a=%E9&%FF=b")
    assert isinstance(hash(query), int)


def test_a_signature_set_with_with_query_reaches_the_wire_escaped():
    uri = URI("http://h/x").with_query({"sig": "ab+cd=="})
    assert uri.as_uri() == "http://h/x?sig=ab%2Bcd%3D%3D"
    assert uri.query.to_dict() == {"sig": ["ab+cd=="]}


# --- a Query is a value, not a str ---------------------------------------------


def test_a_query_is_not_a_str_and_is_not_a_sequence():
    query = Query.parse("a=1&b=2")
    assert not isinstance(query, str)
    for operation in (len, iter, reversed, list, dict, lambda q: q[0]):
        with pytest.raises(TypeError):
            operation(query)
    with pytest.raises(TypeError):
        "".join(query)
    with pytest.raises(TypeError):
        query + "&c=3"


def test_the_constructor_takes_pairs_and_refuses_text():
    with pytest.raises(TypeError, match="Query.parse"):
        Query("a=1")
    with pytest.raises(TypeError, match="Query.parse"):
        Query(b"a=1")
    with pytest.raises(TypeError):
        Query.parse(b"a=1")
    with pytest.raises(TypeError):
        Query.parse(None)
    with pytest.raises(TypeError):
        Query(None)
    assert not Query()
    assert str(Query()) == ""


def test_a_query_is_immutable():
    query = Query.parse("a=1")
    with pytest.raises(AttributeError):
        query._text = "b=2"
    with pytest.raises(AttributeError):
        query.extra = 1
    with pytest.raises(AttributeError):
        del query._text
    assert str(query) == "a=1"


def test_queries_are_equal_and_hash_alike_when_they_decode_to_the_same_pairs():
    plain = Query.parse("a=A&b=1")
    escaped = Query.parse("a=%41&b=1")
    assert plain == escaped and hash(plain) == hash(escaped)
    assert str(plain) != str(escaped)
    assert Query({"a": "A", "b": "1"}) == plain
    assert len({plain, escaped, Query.parse("a=A&b=1")}) == 1
    assert Query.parse("a=1&b=2") != Query.parse("b=2&a=1")
    assert Query.parse("a=1") != Query.parse("a=2")


def test_the_separator_decides_the_pairs_and_so_the_equality():
    # The same text splits into two pairs with ";" and into one with "&".
    split = Query.parse("a=1;b=2", separator=";")
    whole = Query.parse("a=1;b=2")
    assert split.to_pairs() == [("a", "1"), ("b", "2")]
    assert whole.to_pairs() == [("a", "1;b=2")]
    assert split != whole
    # Two spellings of the same pairs are one value whatever the separator.
    assert Query.parse("a=1;b=2", separator=";") == Query.parse("a=1&b=2")


def test_wrapping_a_query_keeps_its_separator_and_encoding():
    original = Query.parse("a=1;b=2", separator=";", encoding="latin-1")
    again = Query(original)
    assert (again.separator, again.encoding) == (";", "latin-1")
    assert str(again) == "a=1;b=2" and again == original
    converted = Query(original, separator="&")
    assert str(converted) == "a=1&b=2" and converted.separator == "&"
    assert converted == original


def test_a_query_is_not_equal_to_anything_that_is_not_a_query():
    query = Query.parse("a=1")
    assert query.__eq__("a=1") is NotImplemented
    assert query != "a=1" and "a=1" != query
    assert (
        query != [("a", "1")] and query != {"a": ["1"]} and query != None
    )  # noqa: E711
    assert query != object()


def test_a_query_prints_as_the_call_that_builds_it():
    assert repr(Query.parse("a=1&b=%26")) == "Query.parse('a=1&b=%26')"
    assert (
        repr(Query.parse("a=1;b=2", separator=";", encoding="latin-1"))
        == "Query.parse('a=1;b=2', separator=';', encoding='latin-1')"
    )
    for query in (
        Query.parse("a=1&b=%26"),
        Query.parse("a=1;b=2", separator=";", encoding="latin-1"),
        Query(),
    ):
        assert eval(repr(query)) == query


def test_parsing_what_a_query_prints_gives_it_back():
    for query in (Query({"k": "a b&c"}), Query.parse("x=%41&y"), Query()):
        assert Query.parse(str(query)) == query
        assert str(Query.parse(str(query))) == str(query)


def test_a_query_is_truthy_when_it_has_text():
    assert Query.parse("a") and not Query.parse("") and not Query()


def test_a_query_copies_and_pickles_with_its_separator_and_encoding():
    query = Query.parse("a=1;b=%E9", separator=";", encoding="latin-1")
    assert copy.copy(query) is query and copy.deepcopy(query) is query
    again = pickle.loads(pickle.dumps(query))
    assert again == query and str(again) == str(query)
    assert (again.separator, again.encoding) == (";", "latin-1")
    assert again.to_pairs() == [("a", "1"), ("b", "\xe9")]
