"""The exceptions of uripath: text that is not a URI is a `URISyntaxError`, an
unregistered scheme an `UnsupportedSchemeError`, and a caller's mistake stays a
plain `ValueError` or `TypeError`."""

from __future__ import annotations

import pytest

import uripath
from uripath import (
    URI,
    URIPath,
    URIPathError,
    URISyntaxError,
    UnsupportedSchemeError,
)
from uripath import exceptions
from uripath.source import Source


def test_the_errors_are_the_values_a_caller_already_catches():
    assert issubclass(URIPathError, Exception)
    assert issubclass(URISyntaxError, (URIPathError, ValueError))
    assert issubclass(UnsupportedSchemeError, (URIPathError, ValueError))
    assert not issubclass(URIPathError, ValueError)


def test_the_root_and_the_exceptions_module_export_the_same_objects():
    for name in ("URIPathError", "URISyntaxError", "UnsupportedSchemeError"):
        assert getattr(uripath, name) is getattr(exceptions, name)
        assert name in exceptions.__all__
        assert name in uripath.__all__
    assert issubclass(exceptions.InsecureTransportWarning, UserWarning)


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("http://h:99999/x", "port out of range"),
        ("http://h:12ab/x", "invalid port"),
        ("http://[::1/x", "mismatched brackets"),
        ("http://[v1.fe80]/x", "address mechanism"),
        ("http://[not-an-address]/x", "invalid IPv6"),
        ("http://[1:2:3]/x", "invalid IPv6"),
    ],
)
def test_text_that_is_not_a_uri_is_a_uri_syntax_error(text, complaint):
    with pytest.raises(URISyntaxError, match=complaint) as caught:
        URI(text).source
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value, URIPathError)


def test_a_syntax_error_names_the_fault_and_not_the_text():
    with pytest.raises(URISyntaxError) as caught:
        URI("http://user:S3CRET@h:99999/x").source
    assert "S3CRET" not in str(caught.value)


def test_a_source_that_is_not_only_a_scheme_and_an_authority_is_a_syntax_error():
    with pytest.raises(URISyntaxError, match="path"):
        Source.parse("http://h/some/path")


def test_a_git_uri_on_a_host_with_no_provider_is_a_syntax_error():
    with pytest.raises(URISyntaxError, match="git:"):
        URIPath("git://example.org/owner/repo")


def test_an_archive_uri_without_the_scheme_of_its_archive_is_a_syntax_error():
    with pytest.raises(URISyntaxError, match="has no scheme"):
        URIPath("zip:plain.zip!/member").exists()


def test_an_unregistered_scheme_is_an_unsupported_scheme_error_listing_the_rest():
    with pytest.raises(UnsupportedSchemeError, match="registered: ") as caught:
        URIPath.scheme_class("nosuchscheme")
    assert isinstance(caught.value, ValueError)
    assert "file" in str(caught.value) and "http" in str(caught.value)


def test_a_callers_mistake_is_not_a_uripath_error():
    with pytest.raises(TypeError) as wrong_type:
        URI(object())
    assert not isinstance(wrong_type.value, URIPathError)
    with pytest.raises(ValueError) as outside:
        URI("http://h/a").relative_to("http://h/b")
    assert not isinstance(outside.value, URIPathError)

    with pytest.raises(ValueError) as taken:

        class Hijack(URIPath):
            __SCHEMES = ("ftp",)

    assert not isinstance(taken.value, URIPathError)
    with pytest.raises(ValueError) as composing:
        str(Source("http", None, "h", 99999))
    assert not isinstance(composing.value, URIPathError)
