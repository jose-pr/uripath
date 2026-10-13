"""The text of a `file:` URI and what `==` compares: an empty authority is not
no authority, so `file:///path` is written back as it was read and is the
spelling `pathlib.Path.as_uri()` gives, and a URI equals the text that names
it."""

from __future__ import annotations

import os
import pathlib

import pytest

from pathlib_next import LocalPath
from uripath import URI, Source, URIPath
from uripath.schemes import FileURIPath

TEXTS = [
    "file:///etc/passwd",
    "file:///",
    "file:///a%20b/c%23d",
    "file://localhost/etc/passwd",
    "file://server/share/x",
    "file:/etc/passwd",
    "file:/",
    "file:rel/x",
    "file:///C:/Windows/win.ini",
    "file:////srv/share/x",
]


@pytest.mark.parametrize("cls", [URI, URIPath])
@pytest.mark.parametrize("text", TEXTS)
def test_a_file_uri_is_written_back_as_it_was_read(cls, text):
    uri = cls(text)
    assert uri.as_uri() == text
    assert str(uri) == text
    assert uri == text
    assert cls(uri.as_uri()) == uri


def test_an_empty_authority_is_not_no_authority():
    with_authority, without = URI("file:///x"), URI("file:/x")
    assert with_authority.source.host == ""
    assert without.source.host is None
    assert with_authority.as_uri() == "file:///x"
    assert without.as_uri() == "file:/x"
    assert with_authority != without
    assert len({with_authority, without}) == 2
    assert str(Source.parse("file://")) == "file://"
    assert str(Source.parse("file:")) == "file:"
    assert Source.parse("file://").host == ""
    assert Source.parse("file:").host is None


def test_a_join_keeps_the_authority_it_started_with():
    assert (URIPath("file:///a") / "b").as_uri() == "file:///a/b"
    assert (URIPath("file:/a") / "b").as_uri() == "file:/a/b"
    assert URIPath("file:///a").parent.as_uri() == "file:///"
    assert URIPath("file:///a").with_name("z").as_uri() == "file:///z"
    assert URI("file:///a", "file:b").as_uri() == "file:///a/b"


def test_a_file_path_is_written_as_pathlib_writes_it(tmp_path):
    target = tmp_path / "a dir" / "un\u00efcode #1%.txt"
    expected = target.as_uri()
    assert expected.startswith("file:///")
    assert FileURIPath(expected).as_uri() == expected
    assert URIPath(target).as_uri() == expected
    assert URIPath(LocalPath(target)).as_uri() == expected
    assert URIPath(expected).filepath == LocalPath(target)
    assert URIPath(expected) == expected
    assert URIPath(expected) == URIPath(LocalPath(target))


def test_the_root_and_the_parents_of_a_local_path_are_written_as_pathlib_writes_them(
    tmp_path,
):
    path = URIPath(LocalPath(tmp_path))
    ancestors = [pathlib.Path(p).as_uri() for p in tmp_path.parents]
    assert [p.as_uri() for p in path.parents] == ancestors


def test_a_relative_local_path_has_no_authority(tmp_path):
    relative = pathlib.Path("rel") / "x"
    assert URIPath(relative).as_uri() == "file:rel/x"
    assert (URIPath(tmp_path) / relative).as_uri() == (tmp_path / relative).as_uri()


# --- == with text ---------------------------------------------------------


@pytest.mark.parametrize("cls", [URI, URIPath])
@pytest.mark.parametrize(
    "text",
    [
        "file:///etc/passwd",
        "HTTP://h/x",
        "http://h/a b",
        "http://h/a%20b",
        "http://h/x?a=1#f",
        "http://h:80/x",
    ],
)
def test_a_uri_equals_the_text_that_names_it(cls, text):
    assert cls(text) == text
    assert text == cls(text)
    assert not cls(text) != text


@pytest.mark.parametrize("cls", [URI, URIPath])
def test_a_uri_does_not_equal_text_that_names_another_resource(cls):
    uri = cls("http://h/a b")
    assert uri != "http://h/a%20c"
    assert uri != "https://h/a b"
    assert uri != ""
    assert cls("") == ""


@pytest.mark.parametrize("text", ["http://h:99999/x", "http://[::1/x", "http://h:x/"])
def test_text_that_is_not_a_uri_is_not_equal_and_does_not_raise(text):
    assert URI("http://h/x") != text
    assert not (URIPath("http://h/x") == text)


def test_a_uri_is_not_equal_to_what_is_not_a_uri_or_text():
    assert URI("file:///x") != 5
    assert URI("file:///x") != pathlib.PurePosixPath("/x")
    assert URI("file:///x") != os.fspath("/x").encode()


def test_equal_uris_hash_alike_and_a_text_that_is_canonical_hashes_as_itself():
    uri = URI("file:///x")
    assert hash(uri) == hash(URIPath("file:///x"))
    assert hash(uri) == hash("file:///x")
    assert {uri, URIPath("file:///x")} == {uri}
