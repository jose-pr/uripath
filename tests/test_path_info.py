"""`Path.info` answers the file-type questions of `pathlib.types.PathInfo` over
at most one following and one non-following `stat()`, and `_copy_from()` lets
Python 3.14's `pathlib.Path.copy()` target any `Path` of this library."""

from __future__ import annotations

import os
import pathlib
import stat as stat_module
import sys

import pytest

from pathlib_next import LocalPath
from pathlib_next.mempath import MemPath
from pathlib_next.path._info import _PathInfo
from pathlib_next import FileStat

OLD = 1_000_000_000


def tree():
    root = MemPath("/m")
    (root / "d").mkdir(parents=True)
    (root / "f.txt").write_text("file")
    (root / "d" / "g.txt").write_text("nested")
    return root


# --- info --------------------------------------------------------------------


class Counting(MemPath):
    """A `MemPath` that counts its stats, and can report a link."""

    __slots__ = ()

    calls: list = []
    links: set = set()

    def stat(self, *, follow_symlinks=True):
        Counting.calls.append((self.name, follow_symlinks))
        if self.name in Counting.links:
            if not follow_symlinks:
                return FileStat(st_mode=stat_module.S_IFLNK | 0o777)
            return FileStat(is_dir=True)
        return super().stat(follow_symlinks=follow_symlinks)


@pytest.fixture
def counting():
    Counting.calls = []
    Counting.links = set()
    root = Counting("/c")
    root.mkdir()
    (root / "f").write_text("x")
    Counting.calls.clear()
    return root


# --- _copy_from: what a path is given by pathlib 3.14's Path.copy() ------------------


STDLIB_HOOKS = (
    "needs Python 3.14, whose pathlib.Path.copy() calls target._copy_from() "
    "after pathlib._os.ensure_distinct_paths(); this pathlib no longer has them"
)


def _stdlib_copy_hooks_exist():
    if sys.version_info < (3, 14):
        return False
    try:
        from pathlib._os import ensure_distinct_paths  # noqa: F401
    except ImportError:
        return False
    return hasattr(pathlib.Path, "_copy_from")


stdlib_copy = pytest.mark.skipif(not _stdlib_copy_hooks_exist(), reason=STDLIB_HOOKS)


@stdlib_copy
def test_stdlib_path_copy_reaches_a_file_uri(tmp_path):
    pytest.importorskip("uritools")
    from uripath.schemes import FileURIPath

    source = tmp_path / "f.txt"
    source.write_text("through a URI")
    target = FileURIPath((tmp_path / "out.txt").as_uri())

    source.copy(target)

    assert (tmp_path / "out.txt").read_text() == "through a URI"
