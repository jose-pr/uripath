"""PathSyncer low-severity soundness regressions (2026-09-15 deep review).

Tolerated errors leave a WARNING record and a `SyncEvent.Error` hook call; a
non-empty target directory is never deleted without `remove_missing`; hooks
receive `PathAndStat` and the real `dry_run` for every event; directory
symlinks are created as directory links; an identical link is left alone;
`PathAndStat` follows symlinks by default. Each test asserts the outcome on
the tree, the log record, or the call the backend received.
"""

import logging
import os
import sys

import pytest

import pathlib_next
from pathlib_next.mempath import MemPath
from pathlib_next import FileStat
from pathlib_next.sync import PathAndStat, PathSyncer, SyncEvent

IS_WINDOWS = sys.platform == "win32"
LOGGER = "pathlib_next.sync"


def _size(entry):
    return entry.stat.st_size


def _symlink(target, link, *, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink unavailable: {error}")


def _recorder():
    events = []

    def hook(source, target, event, dry_run):
        events.append((source, target, event, dry_run))

    return events, hook


def _warnings(caplog):
    return [
        r for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING
    ]


# --- sync-ignored-errors-silent ---------------------------------------------


def _mem_source():
    source = MemPath("/src")
    source.mkdir()
    (source / "a.txt").write_text("a")
    (source / "b.txt").write_text("b")
    return source








def test_deep_tree_is_never_truncated_silently(caplog):
    # The traversal is recursive, so a tree deeper than the interpreter's
    # recursion limit fails with RecursionError. Tolerated, that must at
    # least leave a WARNING; an iterative traversal would reach the leaf.
    source = MemPath("/src")
    target = MemPath("/dst")
    deepest, leaf = source, target
    for depth in range(max(400, sys.getrecursionlimit() // 2)):
        deepest, leaf = deepest / f"d{depth}", leaf / f"d{depth}"
    deepest.mkdir(parents=True)
    (deepest / "leaf.txt").write_text("leaf")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        PathSyncer(_size, ignore_error=True).sync(source, target)

    if not (leaf / "leaf.txt").exists():
        assert RecursionError in [r.exc_info[0] for r in _warnings(caplog)]






# --- sync-type-change-deletes-tree-without-remove-missing -------------------


def _dir_to_file_trees():
    source = MemPath("/src")
    source.mkdir()
    (source / "reports").write_text("now a file")
    (source / "other.txt").write_text("other")
    target = MemPath("/dst")
    (target / "reports").mkdir(parents=True)
    for n in range(3):
        (target / "reports" / f"q{n}.csv").write_text(str(n))
    return source, target


def _csvs(target):
    return sorted(p.name for p in (target / "reports").iterdir())














# --- sync-hook-contract-start-event -------------------------------------------






# --- sync-windows-dir-symlink-broken ------------------------------------------


def _dir_link_source(tmp_path):
    source = tmp_path / "src"
    (source / "z_real").mkdir(parents=True)
    (source / "z_real" / "f.txt").write_text("f")
    (source / "z_file.txt").write_text("x")
    # "a_" sorts first, so the link is created before its target exists at
    # the destination and os.symlink cannot guess the kind.
    _symlink("z_real", source / "a_dirlink", directory=True)
    _symlink("z_file.txt", source / "a_filelink")
    return source








# --- sync-identical-symlink-recreated -------------------------------------------






# --- sync-pathandstat-default-lstat ----------------------------------------------


