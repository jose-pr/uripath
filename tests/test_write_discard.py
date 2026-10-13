"""A write stream that commits on close is not committed when the `with` block
over it raised: the `ftp:` upload and the rewrite of a `zip:` archive, whose
streams are the core's, behave through their URI classes as the `http:` and
`dav:` streams do (tests/test_http_writes.py)."""

from __future__ import annotations

import gc
import zipfile

import pytest

from ftp_loopback import LoopbackFtp
from pathlib_next.ftp import _backend as ftp_mod
from uripath.schemes import FTPURIBackend, FTPURIPath, ZipURIPath

DIRS = {"/", "/pub"}
FILE = "type=file;size=5;modify=20240101000000;"


class Boom(Exception):
    pass


# --- ftp: ----------------------------------------------------------------------------------


@pytest.fixture
def server():
    with LoopbackFtp(
        files={"/pub/x": b"hello"},
        dirs=DIRS,
        entries={"/pub/x": FILE},
        listings={"/pub": f"{FILE} x\r\n".encode()},
    ) as running:
        yield running
        for key in list(ftp_mod._CACHED_CLIENTS.cache):
            if key[1].port == running.port:
                ftp_mod._CACHED_CLIENTS.discard(*key)


def _ftp(server, name):
    return FTPURIPath(f"{server.url}{name}", backend=FTPURIBackend(timeout=5))


def _stor(server):
    return [arg for _, command, arg in server.log if command == "STOR"]


@pytest.mark.parametrize("mode, data", [("wb", b"part"), ("w", "part")])
def test_ftp_a_failed_block_does_not_create_the_file(server, mode, data):
    with pytest.raises(Boom):
        with _ftp(server, "/pub/new").open(mode) as stream:
            stream.write(data)
            raise Boom
    gc.collect()
    assert "/pub/new" not in server.files
    assert _stor(server) == []


@pytest.mark.parametrize("mode, data", [("wb", b"part"), ("w", "part")])
def test_ftp_a_failed_block_leaves_the_old_bytes(server, mode, data):
    with pytest.raises(Boom):
        with _ftp(server, "/pub/x").open(mode) as stream:
            stream.write(data)
            raise Boom
    gc.collect()
    assert server.files["/pub/x"] == b"hello"
    assert _stor(server) == []


@pytest.mark.parametrize("mode, data", [("r+b", b"J"), ("r+", "J")])
def test_ftp_a_failed_read_modify_write_block_leaves_the_old_bytes(server, mode, data):
    with pytest.raises(Boom):
        with _ftp(server, "/pub/x").open(mode) as stream:
            stream.write(data)
            raise Boom
    gc.collect()
    assert server.files["/pub/x"] == b"hello"
    assert _stor(server) == []


@pytest.mark.parametrize("mode, data", [("wb", b"whole"), ("w", "whole")])
def test_ftp_a_block_that_ended_normally_uploads_once(server, mode, data):
    with _ftp(server, "/pub/x").open(mode) as stream:
        stream.write(data)
    assert server.files["/pub/x"] == b"whole"
    assert _stor(server) == ["/pub/x"]


@pytest.mark.parametrize("mode, data", [("wb", b"whole"), ("w", "whole")])
def test_ftp_a_stream_closed_without_a_block_uploads_once(server, mode, data):
    stream = _ftp(server, "/pub/closed").open(mode)
    stream.write(data)
    assert _stor(server) == []
    stream.close()
    stream.close()
    assert server.files["/pub/closed"] == b"whole"
    assert _stor(server) == ["/pub/closed"]


# --- zip: ----------------------------------------------------------------------------------


def _archive(tmp_path, **members):
    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as out:
        for name, data in members.items():
            out.writestr(name, data)
    return archive


def _member(archive, name):
    return ZipURIPath(f"zip:{archive.as_uri()}!/{name}")


def _contents(archive):
    with zipfile.ZipFile(archive) as out:
        return {name: out.read(name) for name in out.namelist()}


@pytest.mark.parametrize("mode, data", [("wb", b"part"), ("w", "part")])
def test_zip_a_failed_block_does_not_add_the_member(tmp_path, mode, data):
    archive = _archive(tmp_path, old=b"OLD")
    before = archive.read_bytes()
    with pytest.raises(Boom):
        with _member(archive, "new").open(mode) as stream:
            stream.write(data)
            raise Boom
    gc.collect()
    assert archive.read_bytes() == before


@pytest.mark.parametrize("mode, data", [("wb", b"part"), ("w", "part")])
def test_zip_a_failed_block_leaves_the_member_it_would_have_replaced(
    tmp_path, mode, data
):
    archive = _archive(tmp_path, old=b"OLD")
    before = archive.read_bytes()
    with pytest.raises(Boom):
        with _member(archive, "old").open(mode) as stream:
            stream.write(data)
            raise Boom
    gc.collect()
    assert archive.read_bytes() == before
    assert _contents(archive) == {"old": b"OLD"}


@pytest.mark.parametrize("mode, data", [("r+b", b"J"), ("r+", "J")])
def test_zip_a_failed_read_modify_write_block_leaves_the_member(tmp_path, mode, data):
    archive = _archive(tmp_path, old=b"OLD")
    before = archive.read_bytes()
    with pytest.raises(Boom):
        with _member(archive, "old").open(mode) as stream:
            stream.write(data)
            raise Boom
    assert archive.read_bytes() == before


def test_zip_a_failed_block_does_not_create_the_archive(tmp_path):
    archive = tmp_path / "missing.zip"
    with pytest.raises(Boom):
        with _member(archive, "new").open("wb") as stream:
            stream.write(b"part")
            raise Boom
    assert not archive.exists()


@pytest.mark.parametrize("mode, data", [("wb", b"whole"), ("w", "whole")])
def test_zip_a_block_that_ended_normally_writes_the_member(tmp_path, mode, data):
    archive = _archive(tmp_path, old=b"OLD")
    with _member(archive, "new").open(mode) as stream:
        stream.write(data)
    assert _contents(archive) == {"old": b"OLD", "new": b"whole"}


@pytest.mark.parametrize("mode, data", [("wb", b"whole"), ("w", "whole")])
def test_zip_a_stream_closed_without_a_block_writes_the_member(tmp_path, mode, data):
    archive = _archive(tmp_path, old=b"OLD")
    stream = _member(archive, "new").open(mode)
    stream.write(data)
    assert _contents(archive) == {"old": b"OLD"}
    stream.close()
    assert _contents(archive) == {"old": b"OLD", "new": b"whole"}
