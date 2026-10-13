"""`as_path`: text read as a local path or as a URI."""

from __future__ import annotations

import pathlib

import pytest

import uripath
from pathlib_next import LocalPath
from uripath import URIPath, as_path
from uripath.schemes import DataURIPath, HTTPURIPath


@pytest.mark.parametrize(
    "text",
    ["12:30.txt", "2024-01-01T10:00:00.log", "notes:draft", "C:/x", "c:x", "./a:b"],
)
def test_text_with_a_colon_that_is_not_a_uri_is_a_local_path(text):
    path = as_path(text)
    assert isinstance(path, LocalPath)
    assert str(path) == str(LocalPath(text))


@pytest.mark.parametrize(
    "text",
    [
        "s3://bucket/key",
        "zip:file:///a.zip!/x",
        "data:,abc",
        "file:relative",
        "unknown-scheme://host/x",
    ],
)
def test_text_with_a_scheme_is_a_uri_path(text):
    path = as_path(text)
    assert isinstance(path, URIPath)
    assert not isinstance(path, LocalPath)
    assert path == URIPath(text, findclass=True)


def test_a_uri_path_is_the_class_its_scheme_registers():
    assert isinstance(as_path("data:,abc"), DataURIPath)
    assert isinstance(as_path("http://127.0.0.1:9/x"), HTTPURIPath)


@pytest.mark.parametrize(
    ("text", "distribution"),
    [
        ("sftp://h/x", "uripath-sftp"),
        ("sftp:x", "uripath-sftp"),
        ("s3://bucket/key", "uripath-objstore"),
        ("gs://bucket/key", "uripath-objstore"),
        ("az://container/blob", "uripath-objstore"),
    ],
)
def test_a_scheme_another_distribution_provides_names_it_on_first_use(
    text, distribution
):
    path = as_path(text)
    assert isinstance(path, URIPath)
    with pytest.raises(ImportError, match=distribution):
        path.stat()


def test_a_relative_name_is_local_and_reads_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert as_path("missing.txt") == LocalPath("missing.txt")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("value", [pathlib.Path("x"), b"x", None, 1])
def test_what_is_not_text_is_a_type_error(value):
    with pytest.raises(TypeError, match="path text"):
        as_path(value)


def test_the_root_exports_it():
    assert "as_path" in uripath.__all__
    assert uripath.as_path is as_path
