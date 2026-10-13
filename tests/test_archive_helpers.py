"""`make_archive`, `unpack_archive` and `detect_format`: what a member holds, how it
is sized and dated, which directories it has, and links that lead nowhere."""

import http.server
import io
import os
import stat as _stat
import sys
import tarfile
import threading
import time
import traceback
import warnings
import zipfile

import pytest

from capabilities import requires_uri_extra
from pathlib_next import LocalPath
from pathlib_next.mempath import MemPath
from pathlib_next.archive import detect_format, make_archive, unpack_archive
from pathlib_next import FileStat

PAYLOAD = bytes(range(256)) * 40  # 10240 bytes


class _SizedWrong(MemPath):
    """A path whose `stat()` reports a size other than its content's."""

    claimed = 0

    def stat(self, *, follow_symlinks=True):
        stat = super().stat(follow_symlinks=follow_symlinks)
        if stat.is_dir():
            return stat
        return FileStat(st_mode=stat.st_mode, st_size=type(self).claimed)


def _read_tar(data: bytes):
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return {
            m.name: (m, tar.extractfile(m).read() if m.isfile() else None)
            for m in tar.getmembers()
        }


def _source(cls=MemPath):
    root = cls("/src")
    root.mkdir()
    (root / "data.bin").write_bytes(PAYLOAD)
    return root


# --- a tar member is as long as what was read -------------------------------


@pytest.mark.parametrize("claimed", [0, len(PAYLOAD) + 5000])
def test_a_zip_member_holds_what_was_read_whatever_stat_says(claimed):
    _SizedWrong.claimed = claimed
    target = MemPath("/out.zip")

    make_archive(_source(_SizedWrong), "zip", target)

    with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as archive:
        assert archive.read("data.bin") == PAYLOAD


@requires_uri_extra
def test_a_tar_of_an_http_file_served_without_a_length_holds_all_its_bytes():
    from uripath import URIPath

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"  # the body ends when the connection does

        def _head(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()

        def do_HEAD(self):
            self._head()

        def do_GET(self):
            self._head()
            self.wfile.write(PAYLOAD)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = URIPath(f"http://127.0.0.1:{server.server_address[1]}/data.bin")
        assert source.stat().st_size == 0
        target = MemPath("/out.tar")
        make_archive(source, "tar", target)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

    member, content = _read_tar(target.read_bytes())["data.bin"]
    assert member.size == len(PAYLOAD)
    assert content == PAYLOAD


# --- directories are members, empty ones too --------------------------------


def _tree():
    root = MemPath("/src")
    (root / "empty").mkdir(parents=True)
    (root / "sub" / "deeper").mkdir(parents=True)
    (root / "sub" / "run.sh").write_bytes(b"#!/bin/sh\n")
    return root


def test_a_zip_lists_each_directory_before_what_is_in_it():
    target = MemPath("/out.zip")
    make_archive(_tree(), "zip", target)

    with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as archive:
        names = archive.namelist()
        assert all(i.is_dir() for i in archive.infolist() if i.filename.endswith("/"))
    assert set(names) == {"empty/", "sub/", "sub/deeper/", "sub/run.sh"}
    assert names.index("sub/") < names.index("sub/run.sh")
    assert names.index("sub/") < names.index("sub/deeper/")


# --- times and permission bits ----------------------------------------------

STAMP = 1_600_000_000  # 2020-09-13


@pytest.fixture
def stamped(tmp_path):
    src = tmp_path / "src"
    (src / "dir").mkdir(parents=True)
    (src / "dir" / "f.txt").write_text("x")
    (src / "top.txt").write_text("y")
    for path in (src / "dir" / "f.txt", src / "top.txt", src / "dir"):
        os.utime(path, (STAMP, STAMP))
    return src


def test_zip_members_carry_the_source_times(stamped):
    target = MemPath("/out.zip")
    make_archive(LocalPath(stamped), "zip", target)

    expected = time.localtime(STAMP)[:6]
    with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as archive:
        dates = {i.filename: i.date_time for i in archive.infolist()}
    # A zip stores seconds in steps of two.
    assert set(dates) == {"dir/", "dir/f.txt", "top.txt"}
    for name, date in dates.items():
        assert date[:5] == expected[:5], name
        assert abs(date[5] - expected[5]) <= 1, name


@pytest.mark.parametrize("fmt", ["zip", "tar"])
def test_a_source_that_reports_no_time_gets_the_default(fmt):
    class NoTime(MemPath):
        def stat(self, *, follow_symlinks=True):
            stat = super().stat(follow_symlinks=follow_symlinks)
            return FileStat(st_mode=stat.st_mode, st_size=stat.st_size, st_mtime=0)

    target = MemPath(f"/out.{fmt}")
    make_archive(_source(NoTime), fmt, target)

    if fmt == "zip":
        with zipfile.ZipFile(io.BytesIO(target.read_bytes())) as archive:
            assert archive.getinfo("data.bin").date_time == (1980, 1, 1, 0, 0, 0)
    else:
        assert _read_tar(target.read_bytes())["data.bin"][0].mtime == 0


# --- links that lead nowhere ------------------------------------------------


def _links_tar(members):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, kind, payload in members:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
                continue
            info.type = {
                "sym": tarfile.SYMTYPE,
                "hard": tarfile.LNKTYPE,
                "dir": tarfile.DIRTYPE,
            }[kind]
            if kind != "dir":
                info.linkname = payload
            tar.addfile(info)
    return buffer.getvalue()


def _unpack(members):
    archive = MemPath("/in.tar")
    archive.write_bytes(_links_tar(members))
    dest = MemPath("/out")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        unpack_archive(archive, dest)
    skipped = sorted(
        str(w.message).split("'")[1]
        for w in caught
        if issubclass(w.category, UserWarning)
    )
    names = {
        child.name: child.read_bytes() for child in dest.iterdir() if child.is_file()
    }
    return names, skipped
