"""A host keeps the spelling it was given, and whatever compares hosts or keys
on one folds the case itself: `http://NASA/x` and `http://nasa/x` are one
server for backend sharing, same-file decisions, redirects, proxy rules and the
connection cache."""

from __future__ import annotations

import pytest

from http_fakes import FakeTransport, reply
from pathlib_next.providers import contains
from uripath import URI, Source, URIPath
from uripath.schemes import FileURIPath, FTPURIBackend, FTPURIPath
from uripath.schemes import GitHubURIPath, GitLabURIPath, HTTPURIPath
from uripath.schemes import _ftp
from uripath.source import compose_host, compose_uri, fold_host, same_authority

TOKEN = "Bearer SECRET-TOKEN"


# --- the text keeps the spelling ------------------------------------------------------


def test_a_host_keeps_the_spelling_it_was_given():
    source = Source.parse("wss://root:pw@nasA:8443")
    assert source.host == "nasA"
    assert str(source) == "wss://root@nasA:8443"
    assert source.reveal() == "wss://root:pw@nasA:8443"
    uri = URI("wss://root:pw@nasA:8443/api")
    assert uri.source.host == "nasA"
    assert str(uri) == "wss://root@nasA:8443/api"
    assert uri.as_uri(sanitize=False) == "wss://root:pw@nasA:8443/api"
    assert repr(URIPath("http://NasA/x")) == "HTTPURIPath('http://NasA/x')"


def test_only_the_scheme_is_folded_by_the_parser():
    uri = URI("HTTP://NasA/Dir/File")
    assert uri.as_uri() == "http://NasA/Dir/File"
    assert uri.source.scheme == "http"


def test_composing_does_not_fold_a_host():
    assert compose_host("NasA") == "NasA"
    assert compose_uri("http", None, "NasA", None, "/x", None, None) == "http://NasA/x"
    assert Source("http", None, "NasA", None).reveal() == "http://NasA"


def test_derived_paths_keep_the_spelling_of_their_host():
    base = URIPath("http://NasA/d/f.txt")
    for derived in (
        base / "g",
        base.parent,
        base.with_name("g"),
        base.with_suffix(".x"),
    ):
        assert derived.source.host == "NasA"
        assert derived.as_uri().startswith("http://NasA/")


def test_an_address_is_not_a_name():
    assert URI("http://[FE80::1]/x").as_uri() == "http://[fe80::1]/x"
    assert URI("http://[::1]/x").source.host.compressed == "::1"


def test_a_non_ascii_host_is_still_written_in_idna_form():
    uri = URI("http://BÜCHER.example/x")
    assert uri.as_uri().startswith("http://xn--bcher-kva.")
    assert uri == URI("http://bücher.example/x")


def test_fold_host_lowers_a_name_and_leaves_an_address_or_nothing():
    assert fold_host("NasA.Example") == "nasa.example"
    assert fold_host("") == ""
    assert fold_host(None) is None
    address = URI("http://[::1]/").source.host
    assert fold_host(address) is address


# --- one server whatever the case -----------------------------------------------------


def test_the_same_authority_is_decided_without_regard_to_the_case_of_the_host():
    assert same_authority(Source.parse("http://NASA"), Source.parse("http://nasa"))
    assert not same_authority(
        Source.parse("http://u@NASA"), Source.parse("http://U@nasa")
    )
    assert not same_authority(
        Source.parse("http://NASA"), Source.parse("http://nasa:81")
    )
    assert not same_authority(Source.parse("http://NASA"), Source.parse("https://nasa"))


@pytest.mark.parametrize("cls", [URI, URIPath])
def test_uris_that_differ_in_the_case_of_the_host_are_equal(cls):
    upper, lower = cls("http://NASA/x?a=1#f"), cls("http://nasa/x?a=1#f")
    assert upper == lower and lower == upper
    assert not upper != lower
    assert hash(upper) == hash(lower)
    assert len({upper, lower}) == 1
    assert upper == "http://nasa/x?a=1#f" and upper == "HTTP://NASA/x?a=1#f"
    assert not upper < lower and not upper > lower
    assert sorted([upper, lower, cls("http://nasa/a")])[0] == cls("http://nasa/a")


@pytest.mark.parametrize(
    "other",
    ["http://nasa/X", "http://nasa/x?A=1", "http://nasa/x#F", "http://u@nasa/x"],
)
def test_everything_but_the_host_name_is_compared_exactly(other):
    assert URI("http://NASA/x?a=1#f") != URI(other)
    assert URI("http://NASA/x") != URI("http://nasa:81/x")


def test_the_text_of_an_equal_uri_is_still_what_it_was_written_with():
    assert URI("http://NASA/x").as_uri() == "http://NASA/x"
    assert URI("http://nasa/x").as_uri() == "http://nasa/x"


def test_relative_to_and_containment_do_not_depend_on_the_case_of_the_host():
    child, parent = URIPath("http://NASA/d/f"), URIPath("http://nasa/d")
    assert child.is_relative_to(parent)
    assert str(child.relative_to(parent)) == "f"
    assert contains(parent, child)
    assert contains(URIPath("http://NASA/d/f"), URIPath("http://nasa/d/f"))
    assert not contains(URIPath("http://NASA/e"), child)


def test_a_join_across_spellings_of_one_host_keeps_the_first_and_its_backend():
    backend = object()
    base = URIPath("http://NASA/d/", backend=backend)
    joined = base / URIPath("http://nasa/x")
    assert joined.backend is backend
    assert joined.source.host == "NASA"
    assert URIPath("http://NASA/a", URIPath("http://nasa/b")).source.host == "NASA"


def test_paths_that_differ_in_the_case_of_the_host_share_the_backend_they_derive():
    first = URIPath("http://NASA/a")
    second = URIPath(first, "http://nasa/b")
    assert second.source.host == "NASA"
    assert second.backend is first.backend
    assert URIPath(first, "http://other/b").backend is not first.backend


def test_a_rename_within_one_server_is_not_a_move_to_another():
    source = URIPath("dav://NASA/d/a.txt")
    assert source._rename_target(URIPath("dav://nasa/d/b.txt")).source.host == "nasa"
    with pytest.raises(NotImplementedError):
        source._rename_target(URIPath("dav://other/d/b.txt"))


def test_paths_of_one_server_are_one_filesystem_whatever_the_case():
    first, second = URIPath("http://NASA/x"), URIPath("http://nasa/x")
    assert first._same_filesystem(second)
    backend = object()
    assert URIPath("http://NASA/x", backend=backend)._same_filesystem(
        URIPath("http://nasa/x", backend=backend)
    )


# --- redirects, local host, proxy rules -----------------------------------------------


def _redirect(location):
    transport = FakeTransport(
        {
            ("HEAD", "http://NASA/a"): reply(302, headers={"Location": location}),
            ("HEAD", "http://nasa/b"): reply(200),
            ("HEAD", "http://other/b"): reply(200),
        }
    )
    path = HTTPURIPath("http://NASA/a").with_transport(
        transport, headers={"Authorization": TOKEN}
    )
    path.stat()
    return [(call.url, call.headers.get("Authorization")) for call in transport.sent]


def test_a_redirect_to_the_same_host_in_another_case_keeps_authorization():
    assert _redirect("http://nasa/b") == [
        ("http://NASA/a", TOKEN),
        ("http://nasa/b", TOKEN),
    ]


def test_a_redirect_to_another_host_does_not_carry_authorization():
    assert _redirect("http://other/b") == [
        ("http://NASA/a", TOKEN),
        ("http://other/b", None),
    ]


def test_localhost_is_this_machine_in_any_case(monkeypatch):
    from uripath.source import _locality

    def never(host):
        raise AssertionError(f"{host!r} was looked up")

    monkeypatch.setattr(_locality, "_resolve_is_local", never)
    for host in ("localhost", "LocalHost", "LOCALHOST"):
        assert Source("http", None, host, None).is_local()
        assert URIPath(f"http://{host}/x").is_local()


def test_the_answer_for_a_host_is_remembered_once_for_every_spelling(monkeypatch):
    from uripath.source import _locality

    asked = []
    monkeypatch.setattr(_locality, "_local_cache", {})
    monkeypatch.setattr(
        _locality, "_resolve_is_local", lambda host: asked.append(host) or False
    )
    for host in ("NasA.example", "nasa.EXAMPLE", "nasa.example"):
        assert Source("http", None, host, None).is_local() is False
    assert asked == ["nasa.example"]


@pytest.mark.parametrize("host", ["LOCALHOST", "localhost", "LocalHost"])
def test_a_file_uri_on_localhost_is_a_local_path_in_any_case(host, tmp_path):
    (tmp_path / "f.txt").write_text("x")
    path = FileURIPath(
        f"file://{host}{tmp_path.as_uri().removeprefix('file://')}/f.txt"
    )
    assert path.read_text() == "x"


# --- the connection cache -------------------------------------------------------------


def test_ftp_paths_to_one_server_share_a_connection_key_whatever_the_case():
    backend = FTPURIBackend(timeout=5)
    first = FTPURIPath("ftp://NAS:2121/pub/a", backend=backend)
    second = FTPURIPath("ftp://nas:2121/pub/b", backend=backend)
    assert first._core_path.backend is second._core_path.backend
    assert first._core_path.backend.endpoint.host == "nas"
    other = FTPURIPath("ftp://nas2:2121/pub/b", backend=backend)
    assert other._core_path.backend is not first._core_path.backend
    assert _ftp._endpoint(first.source).port == 2121


# --- tables keyed on a host -----------------------------------------------------------


@pytest.mark.parametrize("host", ["github.com", "GitHub.com", "WWW.GITHUB.COM"])
def test_github_com_is_github_com_in_any_case(host):
    path = GitHubURIPath(f"github://{host}/o/r/x")
    assert path._default_api_base() == "https://api.github.com"
    assert isinstance(URIPath(f"git://{host}/o/r/x"), GitHubURIPath)


def test_gitlab_com_is_gitlab_com_in_any_case():
    assert isinstance(URIPath("git://GitLab.COM/o/r/x"), GitLabURIPath)
    assert isinstance(URIPath("git://WWW.gitlab.com/o/r/x"), GitLabURIPath)


def test_a_self_hosted_api_root_is_the_same_whatever_the_case():
    upper = GitHubURIPath("github://GHE.Example:8443/o/r/x")
    lower = GitHubURIPath("github://ghe.example:8443/o/r/x")
    assert upper._default_api_base() == lower._default_api_base()
    assert upper._default_api_base() == "https://ghe.example:8443/api/v3"
