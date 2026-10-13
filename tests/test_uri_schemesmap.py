"""`schemesmap=` is the allow-list of classes a path dispatches to: the path
keeps it, and every class chosen after construction -- a join with a URI, a
new source, a `copy()`/`move()` string destination, an archive's outer URI --
is chosen from it. It restricts dispatch only; it is not a sandbox."""

from __future__ import annotations

import zipfile

import pytest

pytest.importorskip("uritools")

from uripath import URIPath
from uripath.schemes import DataURIPath, FileURIPath, FTPURIPath, ZipURIPath
from uripath.source import Source

ALLOW = {"data": DataURIPath, "zip": ZipURIPath}
FTP_ONLY = {"ftp": FTPURIPath}


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "a.zip"
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("m.txt", "member")
    return path


def test_a_construction_with_a_map_dispatches_from_the_map_only():
    assert type(URIPath("data:,x", schemesmap=ALLOW)) is DataURIPath
    assert type(URIPath("file:///tmp/x", schemesmap=ALLOW)) is URIPath
    assert type(URIPath("file:///tmp/x")) is FileURIPath


def test_a_zip_path_opens_its_outer_archive_through_the_map(archive):
    url = f"zip:{archive.as_uri()}!/m.txt"
    assert URIPath(url).read_text() == "member"
    allowing = dict(ALLOW, file=FileURIPath)
    assert URIPath(url, schemesmap=allowing).read_text() == "member"
    restricted = URIPath(url, schemesmap=ALLOW)
    assert type(restricted.backend.outer) is URIPath
    with pytest.raises(NotImplementedError):
        restricted.read_text()


def test_a_restricted_zip_path_does_not_borrow_a_handle_another_path_opened(archive):
    url = f"zip:{archive.as_uri()}!/m.txt"
    open_elsewhere = URIPath(url)
    assert open_elsewhere.read_text() == "member"
    restricted = URIPath(url, schemesmap=ALLOW)
    assert restricted.backend is not open_elsewhere.backend
    with pytest.raises(NotImplementedError):
        restricted.exists()


def test_a_derived_zip_path_keeps_the_map(archive):
    restricted = URIPath(f"zip:{archive.as_uri()}!/", schemesmap=ALLOW)
    member = restricted / "m.txt"
    assert member._schemes_in_use is ALLOW
    with pytest.raises(NotImplementedError):
        member.read_text()


def test_a_string_destination_with_a_scheme_is_dispatched_from_the_map(tmp_path):
    target = tmp_path / "out.txt"
    source = URIPath("data:,hello", schemesmap=ALLOW)
    with pytest.raises(NotImplementedError):
        source.copy(target.as_uri())
    assert not target.exists()
    assert type(source._coerce_target(target.as_uri())) is URIPath
    assert type(source._coerce_target("data:,x")) is DataURIPath
    # Without a map the same destination is a local file again.
    URIPath("data:,hello").copy(target.as_uri())
    assert target.read_text() == "hello"


def test_a_join_with_a_uri_argument_chooses_its_class_from_the_map():
    base = URIPath("ftp://h/dir", schemesmap=FTP_ONLY)
    other = URIPath("file:///tmp/x")
    assert type(base / other) is URIPath
    assert type(base.joinpath(other)) is URIPath
    assert type(base.parent / other) is URIPath
    assert (base / other)._schemes_in_use is FTP_ONLY
    assert type(URIPath("ftp://h/dir") / other) is FileURIPath
    assert type(base / "child") is FTPURIPath


def test_with_source_chooses_its_class_from_the_map():
    path = URIPath("ftp://h/dir", schemesmap=FTP_ONLY)
    moved = path.with_source(Source("file", None, "", None))
    assert type(moved) is URIPath
    assert moved._schemes_in_use is FTP_ONLY
    assert type(path.with_source(Source("ftp", None, "other", None))) is FTPURIPath
    assert type(URIPath("ftp://h/dir").with_source(Source("file", None, "", None))) is (
        FileURIPath
    )


def test_a_map_restricts_dispatch_and_nothing_a_built_class_does(tmp_path):
    local = FileURIPath((tmp_path / "f.txt").as_uri())
    restricted = URIPath("data:,y", schemesmap=ALLOW)
    # A path the caller built itself is theirs to use.
    restricted.copy(local)
    assert local.read_text() == "y"
