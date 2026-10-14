"""Operations must reach the location they name.

rename()/move() used the SOURCE's connection, bucket or archive with only
`target.path`, so a target on another host, bucket, container, archive or
scheme was renamed in the wrong place and nothing raised. A backend taken
from a join segment also followed an absolute URI to another host, carrying
its session credentials or token there. Each test asserts where the data (or
the backend) actually ended up.
"""

import errno
import zipfile

import pytest

import pathlib_next
from http_fakes import on_current_transport
from pathlib_next.mempath import MemPath


from uripath import Source, URIPath  # noqa: E402

LocalPath = pathlib_next.LocalPath


# --- backend inheritance --------------------------------------------------


def test_http_session_backend_does_not_follow_join_to_another_host():
    """A credential-bearing session must never reach another host.

    A `str` join cannot take one there at all: it names a path on THIS host
    (`URI._join_arg`), so the session stays and so does the host. Only a
    `URI` argument crosses, and then the backend is dropped."""
    base = on_current_transport(
        URIPath("http://trusted.invalid/api/"),
        headers={"Authorization": "Bearer s3cret"},
    )
    assert (base / "child").backend is base.backend

    literal = base / "http://other.invalid/steal"
    assert literal.source.host == "trusted.invalid"
    # The empty segment is kept (RFC 3986 3.3); the point is that the host
    # is unchanged.
    assert literal.path == "/api/http://other.invalid/steal"
    assert literal.backend is base.backend  # still the trusted host

    for crossing in (
        base / URIPath("http://other.invalid/steal"),
        URIPath(base, URIPath("http://other.invalid/steal")),
    ):
        assert crossing.source.host == "other.invalid"
        assert crossing.backend is not base.backend


def test_with_source_keeps_backend_only_for_the_same_authority():
    base = on_current_transport(
        URIPath("http://trusted.invalid/api/"),
        headers={"Authorization": "Bearer s3cret"},
    )
    same = base.with_source(Source("http", None, "trusted.invalid", None))
    other = base.with_source(Source("http", None, "other.invalid", None))
    assert same.backend is base.backend
    assert other.backend is not base.backend


# --- rename() refuses other locations ------------------------------------


def test_ftp_rename_to_another_server_raises_not_implemented():
    src = URIPath("ftp://a.invalid/report.csv")
    with pytest.raises(NotImplementedError):
        src.rename(URIPath("ftp://b.invalid/sub/report.csv"))


# --- archives -------------------------------------------------------------


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def test_zip_member_move_to_local_path_extracts_it(tmp_path):
    archive = _zip(tmp_path / "a.zip", {"x.txt": "X", "keep.txt": "K"})
    member = URIPath(f"zip:{archive.as_uri()}!/x.txt")
    out = LocalPath(tmp_path / "out.txt")
    member.move(out)
    assert out.read_text() == "X"
    with zipfile.ZipFile(archive) as z:
        assert sorted(z.namelist()) == ["keep.txt"]


def test_zip_member_rename_into_another_archive_raises(tmp_path):
    a = _zip(tmp_path / "a.zip", {"x.txt": "X"})
    b = _zip(tmp_path / "b.zip", {"y.txt": "Y"})
    member = URIPath(f"zip:{a.as_uri()}!/x.txt")
    with pytest.raises(NotImplementedError):
        member.rename(URIPath(f"zip:{b.as_uri()}!/x.txt"))
    with zipfile.ZipFile(a) as z:
        assert z.namelist() == ["x.txt"]
    with zipfile.ZipFile(b) as z:
        assert z.namelist() == ["y.txt"]


# --- file: ----------------------------------------------------------------


def test_file_uri_rename_relative_str_is_a_sibling_rename(tmp_path, monkeypatch):
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_text("A")
    result = URIPath(LocalPath(data / "a.txt")).rename("b.txt")
    assert (data / "b.txt").read_text() == "A"
    assert not (elsewhere / "b.txt").exists()
    assert type(result).__name__ == "FileURIPath"


def test_file_uri_rename_to_remote_target_raises(tmp_path):
    (tmp_path / "a.txt").write_text("A")
    src = URIPath(LocalPath(tmp_path / "a.txt"))
    with pytest.raises(NotImplementedError):
        src.rename(URIPath("ftp://host.invalid/srv/a.txt"))
    assert (tmp_path / "a.txt").read_text() == "A"


# --- Path.move() ----------------------------------------------------------
