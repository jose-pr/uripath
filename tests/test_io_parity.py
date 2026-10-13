"""I/O parity with pathlib for the generic `Path` implementations: `touch()`
(no default chmod, no truncation, FileURIPath umask/mtime) and
`copy(preserve_metadata=True)` (only a backend-reported mode is applied).
"""

import os
import stat

import pytest
from capabilities import requires_posix_modes

import pathlib_next
from pathlib_next.mempath import MemPath
from uripath import URIPath
from pathlib_next import FileStat
from pathlib_next.sync import PathSyncer

# --- touch() on a generic backend -----------------------------------------


class _ChmodRecordingMemPath(MemPath):
    """MemPath with a chmod() that records its calls, standing in for any
    backend whose chmod is a verbatim remote setstat (SFTP, FTP SITE CHMOD)."""

    def chmod(self, mode, *, follow_symlinks=True):
        self.backend.setdefault("__chmod_calls__", []).append(mode)


def _chmod_calls(path):
    return path.backend.get("__chmod_calls__", [])


class _FlakyStatMemPath(MemPath):
    """stat() fails once with the given error, then behaves normally."""

    def stat(self, *, follow_symlinks=True):
        pending = self.backend.pop("__stat_error__", None)
        if pending is not None:
            raise pending
        return super().stat(follow_symlinks=follow_symlinks)


# --- FileURIPath.touch delegates to pathlib ------------------------------------


def _file_uri(path):
    return URIPath(pathlib_next.LocalPath(path))


def test_fileuri_touch_does_not_chmod(tmp_path, monkeypatch):
    calls = []
    real_chmod = pathlib_next.LocalPath.chmod

    def spy(self, mode, *, follow_symlinks=True):
        calls.append(mode)
        return real_chmod(self, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(pathlib_next.LocalPath, "chmod", spy)
    uri = _file_uri(tmp_path / "new.txt")
    assert type(uri).__name__ == "FileURIPath"
    uri.touch()
    uri2 = _file_uri(tmp_path / "new2.txt")
    uri2.touch(exist_ok=False)
    assert (tmp_path / "new.txt").is_file()
    assert (tmp_path / "new2.txt").is_file()
    assert calls == []


@requires_posix_modes
def test_fileuri_touch_mode_is_umask_masked_like_pathlib(tmp_path):
    old = os.umask(0o022)
    try:
        _file_uri(tmp_path / "default.txt").touch()
        _file_uri(tmp_path / "explicit.txt").touch(0o666)
    finally:
        os.umask(old)
    assert stat.S_IMODE(os.stat(tmp_path / "default.txt").st_mode) == 0o644
    assert stat.S_IMODE(os.stat(tmp_path / "explicit.txt").st_mode) == 0o644


def test_fileuri_touch_bumps_mtime_of_existing_file(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("keep")
    os.utime(f, (1000, 1000))
    _file_uri(f).touch()
    assert os.stat(f).st_mtime > 1000
    assert f.read_text() == "keep"


def test_fileuri_touch_exist_ok_false_raises(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("keep")
    with pytest.raises(FileExistsError):
        _file_uri(f).touch(exist_ok=False)
    assert f.read_text() == "keep"


# --- FileStat.mode_known ---------------------------------------------------


# --- copy(preserve_metadata=True) ------------------------------------------


def _writable(path):
    return os.access(path, os.W_OK)
