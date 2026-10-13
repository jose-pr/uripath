"""PathSyncer must never destroy data outside what it was asked to mirror.

Every test asserts that the data which must survive actually survives -- a
raised error alone proves nothing, the defects covered here raised nothing.
"""

import io
import os
import sys

import pytest
from capabilities import requires_fifos, requires_junctions

import pathlib_next
from pathlib_next.mempath import MemPath
from pathlib_next.sync import PathSyncer, SyncEvent

IS_WINDOWS = sys.platform == "win32"


def _size(entry):
    return entry.stat.st_size


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _symlink(target, link, *, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink unavailable: {error}")


def _collect():
    calls = []

    def ignore(error, source, target, event):
        calls.append((error, source, target, event))
        return True

    return calls, ignore


# --- sync-missing-root-source-wipes-target ---------------------------------


def test_missing_root_source_cli_keeps_target(tmp_path, capsys):
    pytest.importorskip("duho")
    from uripath.cli import main

    target = tmp_path / "backup"
    _write(target / "file.txt", "precious")
    code = main(["sync", "--remove-missing", str(tmp_path / "buidl"), str(target)])
    assert code == 1
    assert "FileNotFoundError" in capsys.readouterr().err
    assert (target / "file.txt").read_text() == "precious"


# --- sync-child-name-escapes-destination -----------------------------------


def _listing_mempath(extra_names):
    class ListingMemPath(MemPath):
        def _scandir(self):
            yield from super()._scandir()
            if self.as_posix() == "/src":
                for name in extra_names:
                    yield name, None

    return ListingMemPath


def _escape_layout(tmp_path):
    mirror = tmp_path / "mirror"
    dst = mirror / "dst"
    dst.mkdir(parents=True)
    _write(mirror / "precious.txt", "precious")
    _write(tmp_path / "sibling" / "keep.txt", "keep")
    return mirror, dst


def _assert_nothing_escaped(tmp_path, mirror):
    assert (mirror / "precious.txt").read_text() == "precious"
    assert (tmp_path / "sibling" / "keep.txt").read_text() == "keep"
    assert sorted(p.name for p in mirror.iterdir()) == ["dst", "precious.txt"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mirror", "sibling"]


# --- sync-unknown-stat-treated-as-missing ----------------------------------


class _NoStatMemPath(MemPath):
    """Lists like GitLab: every entry's stat is unknown (None)."""

    def _scandir(self):
        for name, _ in super()._scandir():
            yield name, None


# --- sync-target-symlinks-escape-tree (mechanism a) ------------------------


# --- sync-overlapping-source-target ----------------------------------------


# --- more PathSyncer soundness cases -----------------------------------------

import errno
import stat as stat_module

from pathlib_next import FileStat


def _events():
    events = []

    def hook(source, target, event, dry_run):
        source = source.path
        target = target.path
        events.append((event, str(source), str(target), dry_run))

    return events, hook


# sync-symlink-preserve-deletes-before-failing


# sync-copy-not-atomic


class _ResetStream(io.RawIOBase):
    """Serves one chunk, then fails like a dropped connection."""

    def __init__(self, data):
        self._data = data
        self._reads = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        self._reads += 1
        if self._reads > 1:
            raise ConnectionResetError(errno.ECONNRESET, "connection reset")
        chunk = self._data[:4]
        buffer[: len(chunk)] = chunk
        return len(chunk)


class _FlakyMemPath(MemPath):
    def _open(self, mode="r", buffering=-1):
        handle = super()._open(mode, buffering)
        if mode == "r" and self.name == "data.bin":
            return _ResetStream(handle.read())
        return handle


def _flaky_source():
    source = _FlakyMemPath("/src")
    source.mkdir()
    (source / "data.bin").write_bytes(b"NEW! content of a different size")
    return source


# sync-dry-run-crashes


def _mutations(events):
    mutating = {
        SyncEvent.Copy,
        SyncEvent.RemovedMissing,
        SyncEvent.CreatedDirectory,
        SyncEvent.TypeMismatch,
        SyncEvent.Symlink,
    }
    return [(e, s, t) for e, s, t, _ in events if e in mutating]


# sync-removedmissing-event-reports-parent


# sync-error-policy-duplicated-and-misattributed


def _nested_trees(tmp_path):
    source = MemPath("/src")
    (source / "l1" / "l2").mkdir(parents=True)
    (source / "l1" / "l2" / "f.txt").write_text("source")
    target = tmp_path / "dst"
    _write(target / "l1" / "l2" / "f.txt", "target")
    return source, pathlib_next.LocalPath(target)


# sync-special-files-treated-as-directories


class _FifoMemPath(MemPath):
    """Reports the entry named "fifo" as a named pipe."""

    def stat(self, *, follow_symlinks=True):
        result = super().stat(follow_symlinks=follow_symlinks)
        if self.name == "fifo":
            return FileStat(st_mode=stat_module.S_IFIFO | 0o644)
        return result

    def _scandir(self):
        for name, _ in super()._scandir():
            yield name, None


# --- a listed entry is never "missing" ---------------------------------------

from pathlib_next.sync import PathAndStat


def _dangling_layout(tmp_path):
    """A source whose `data` and `file.txt` are links to nothing (an
    unmounted volume), over a target that holds the real thing."""
    src = tmp_path / "src"
    _write(src / "keep.txt", "keep")
    _symlink(tmp_path / "not-mounted", src / "data", directory=True)
    _symlink(tmp_path / "gone.txt", src / "file.txt")
    dst = tmp_path / "dst"
    _write(dst / "data" / "precious.txt", "precious")
    _write(dst / "file.txt", "precious too")
    return src, dst


class _ScanMemPath(MemPath):
    """Lists like a stdlib scandir: entries with a `stat()` method."""

    def _scandir(self):
        class Entry:
            def __init__(self, name, path):
                self.name, self._path = name, path

            def stat(self, *, follow_symlinks=True):
                return self._path.stat(follow_symlinks=follow_symlinks)

        for name, _ in super()._scandir():
            yield Entry(name, self / name)


# --- the error policy receives the public entry type ------------------------


class _StatDenied(MemPath):
    def stat(self, *, follow_symlinks=True):
        raise PermissionError(errno.EACCES, "denied", str(self))


# --- a binding inside the target is replaced, never listed or written through


def _junction(target, link):
    """A Windows junction at `link` naming `target`, both under tmp_path."""
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


@pytest.fixture
def mount_named_mounted(monkeypatch):
    """`is_mount()` answers True for a directory called `mounted`; creating a
    real mount point needs privileges."""
    real_is_mount = pathlib_next.LocalPath.is_mount

    def fake_is_mount(self):
        return self.name == "mounted" or real_is_mount(self)

    monkeypatch.setattr(pathlib_next.LocalPath, "is_mount", fake_is_mount)


def _mutations_below(events, directory):
    return [
        (e, t) for e, s, t in _mutations(events) if t.startswith(directory + os.sep)
    ]


def _mount_trees(tmp_path):
    """A source with a `mounted` directory and a file, over a target whose
    `mounted` directory (a mount point in these tests) holds data of its own."""
    src = tmp_path / "src"
    _write(src / "mounted" / "new.txt", "new")
    _write(src / "own.txt", "own")
    dst = tmp_path / "dst"
    _write(dst / "mounted" / "theirs.txt", "theirs")
    return pathlib_next.LocalPath(src), pathlib_next.LocalPath(dst), dst


# --- the temporary sibling: replace fallback, name length, leftovers -------

import re
import time

from pathlib_next.mempath import MemPathBackend
from pathlib_next.sync._replace import _is_leftover, _temp_sibling

DAY = 24 * 60 * 60


class _RenamingMemPath(MemPath):
    """A MemPath with `rename()`, replacing an existing target."""

    def rename(self, target):
        target = target if isinstance(target, MemPath) else self.with_segments(target)
        parent, name = self._parent_container()
        target_parent, target_name = target._parent_container()
        target_parent[target_name] = parent.pop(name)
        return target


class _RefusingMemPath(_RenamingMemPath):
    """Refuses to rename onto an existing target, as SFTP without POSIX
    rename does."""

    def rename(self, target):
        target = target if isinstance(target, MemPath) else self.with_segments(target)
        if target.exists():
            raise FileExistsError(errno.EEXIST, "exists", str(target))
        return super().rename(target)


class _DroppingMemPath(_RefusingMemPath):
    """Refuses an existing target, and then the connection drops during the
    rename of a temporary file."""

    def rename(self, target):
        if _is_leftover(self.name) and not self.with_segments(target).exists():
            raise ConnectionResetError(errno.ECONNRESET, "connection reset")
        return super().rename(target)


def _mem_pair(target_cls, old="OLD VERSION", new="NEW VERSION!"):
    backend = MemPathBackend()
    target = target_cls("/dst", backend=backend)
    target.mkdir()
    (target / "f.txt").write_text(old)
    source = MemPath("/src")
    source.mkdir()
    (source / "f.txt").write_text(new)
    return source, target, backend


def _leftovers(directory):
    return sorted(name for name in directory if _is_leftover(name))


class _FailingRenameLocal(pathlib_next.LocalPath):
    """A local path whose rename of a temporary file fails."""

    def rename(self, target):
        if _is_leftover(self.name):
            raise ConnectionResetError(errno.ECONNRESET, "connection reset")
        return super().rename(target)


# the temporary name fits where the name does


def _limited(max_bytes=255):
    """A renaming MemPath that refuses to create a name longer than a
    filesystem accepts, recording every name it was asked to create."""

    class Limited(_RenamingMemPath):
        created = []

        def _open(self, mode="r", buffering=-1):
            if mode != "r":
                type(self).created.append(self.name)
                if len(self.name.encode("utf-8")) > max_bytes:
                    raise OSError(errno.ENAMETOOLONG, "name too long", str(self))
            return super()._open(mode, buffering)

    return Limited


# leftovers of a killed run


def _put(directory, name, text="partial", age=0.0):
    """A file in a MemPath directory, last modified `age` seconds ago (0 for
    an unknown time)."""
    path = directory / name
    path.write_text(text)
    parent, key = path._parent_container()
    parent[key].mtime = time.time() - age if age else 0.0
    return path


STALE = ".big.bin.aaaaaaaaaaaa.pathlib-next-tmp"
FRESH = ".big.bin.bbbbbbbbbbbb.pathlib-next-tmp"


@pytest.fixture
def leftover_layout():
    backend = MemPathBackend()
    target = _RenamingMemPath("/dst", backend=backend)
    target.mkdir()
    _put(target, "big.bin", "old")
    _put(target, STALE, age=2 * DAY)
    _put(target, FRESH, age=3600)
    _put(target, "x-tmp", age=2 * DAY)
    _put(target, ".big.bin.nothex.pathlib-next-tmp", age=2 * DAY)
    (target / ".dir.cccccccccccc.pathlib-next-tmp").mkdir()
    source = MemPath("/src")
    source.mkdir()
    (source / "big.bin").write_text("new content, longer")
    return source, target, backend


# --- a dry run refuses what the real run refuses ------------------------------


def _link_source(tmp_path):
    source = tmp_path / "src"
    _write(source / "a.txt", "aaa")
    _symlink("a.txt", source / "lnk")
    _write(source / "z.txt", "zzz")
    return pathlib_next.LocalPath(source)


# --- overlap is decided by where a path is, not how it is spelled ------------


def _mem_tree():
    backend = MemPathBackend()
    root = MemPath("/r", backend=backend)
    (root / "in").mkdir(parents=True)
    (root / "keep.txt").write_text("keep")
    # `/x/../r` is another spelling of `/r` only while `/x` is a directory.
    MemPath("/x", backend=backend).mkdir()
    return backend, root
