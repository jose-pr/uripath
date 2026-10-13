"""An empty segment inside a joined key is a segment (RFC 3986 3.3), whichever
way the join is spelled: a `str` key, a `URI` argument, the constructor or
the finished URI text give the same URI."""

from __future__ import annotations

import pytest

pytest.importorskip("uritools")

from uripath import URI, URIPath

BASES = [
    "http://h/d",
    "http://h/d/",
    "http://h",
    "http://h/",
    "s3://bucket/prefix",
    "sftp://u@h:22/srv",
    "file:///tmp/d",
    "a",
    "a/",
    "/",
    "/abs",
]
KEYS = ["x//y", "x///y", "x//", "x//y/", "a/b//c/d", "p//q//r"]


@pytest.mark.parametrize("base", BASES)
@pytest.mark.parametrize("key", KEYS)
def test_the_four_spellings_of_a_join_agree(base, key):
    by_str = URI(base) / key
    by_joinpath = URI(base).joinpath(key)
    by_uri = URI(base) / URI(key)
    by_constructor = URI(base, key)
    text = by_str.as_uri()
    assert by_joinpath.as_uri() == by_uri.as_uri() == by_constructor.as_uri() == text
    assert "//" in by_str.path[1:], by_str.path
    assert URI(text).path == by_str.path
    assert by_str.segments == by_constructor.segments
    path_base = URIPath(base)
    assert (path_base / key).as_uri() == text
    assert path_base.joinpath("", key).as_uri() == text


def test_the_empty_segment_is_part_of_the_name_and_the_parent():
    joined = URI("http://h/d") / "x//y"
    assert joined.as_uri() == "http://h/d/x//y"
    assert joined.segments == ("", "d", "x", "", "y")
    assert joined.name == "y"
    assert joined.parent.as_uri() == "http://h/d/x/"
    assert joined.parent.parent.as_uri() == "http://h/d/x"


def test_an_absolute_key_restarts_and_keeps_its_empty_segments():
    base = URI("http://h/d/e")
    assert (base / "/x//y").path == "/x//y"
    assert (base / "/x//y").as_uri() == "http://h/x//y"
    assert (base / "/").path == "/"
    assert (base / "/x/").path == "/x/"


def test_a_trailing_slash_is_still_kept_and_two_are_two():
    base = URI("http://h/d")
    assert (base / "x/").path == "/d/x/"
    assert (base / "x//").path == "/d/x//"
    assert (base / "x").path == "/d/x"


def test_a_single_slash_between_names_is_unchanged():
    base = URI("http://h/d")
    assert (base / "x/y/z").path == "/d/x/y/z"
    assert (base / "x" / "y").path == "/d/x/y"
    assert base.joinpath("x", "y/z").path == "/d/x/y/z"


def test_dot_segments_and_empty_segments_in_one_key():
    base = URI("http://h/d")
    for key in ("x//../y", "x/./y//z", "x//y/..", "../x//y"):
        assert (base / key).as_uri() == URI("http://h/d", key).as_uri(), key
    assert (base / "x//../y").path == "/d/x/y"
    assert (base / "x/./y//z").path == "/d/x/y//z"


def test_an_empty_key_and_an_empty_argument_change_nothing():
    base = URI("http://h/d")
    assert (base / "").as_uri() == "http://h/d"
    assert base.joinpath("", "x", "").as_uri() == "http://h/d/x"


def test_a_str_destination_keeps_its_empty_segment_like_a_join(tmp_path):
    path = URIPath((tmp_path / "f").as_uri())
    target = path._rename_target("a//b")
    assert target.path.endswith("/a//b")
    assert target.as_uri() == (path.parent / "a//b").as_uri()
