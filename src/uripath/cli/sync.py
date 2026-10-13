"""`uripath sync`: make a target tree match a source tree."""

from __future__ import annotations

import io as _io

from pathlib_next.sync import PathSyncer, SyncEvent

from .. import as_path, copy_stream
from ._common import Command, stdout

__all__ = ["Sync"]


_ACTIONS = {
    SyncEvent.Copy: "copy",
    SyncEvent.RemovedMissing: "remove",
    SyncEvent.CreatedDirectory: "mkdir",
    SyncEvent.TypeMismatch: "replace",
    SyncEvent.Symlink: "symlink",
}


class Sync(Command):
    """Make TARGET match SOURCE, comparing file content; nothing is deleted unless --remove-missing."""

    _parsername_ = "sync"

    source: str
    "The directory or URI to copy from. Required"
    ("source",)

    target: str
    "The directory or URI to make match SOURCE. Required"
    ("target",)

    dry_run: bool = False
    "Print what would change without changing anything. Omitted: make the changes"
    ("--dry-run",)

    remove_missing: bool = False
    "Delete the entries of TARGET that SOURCE does not have. Omitted: keep them"
    ("--remove-missing",)

    size_only: bool = False
    "Compare file sizes only, which misses same-size edits. Omitted: compare content"
    ("--size-only",)

    follow_symlinks: bool = True
    "Copy what a symbolic link points to. With --no-follow-symlinks: recreate the link"
    ("--follow-symlinks",)

    follow_mounts: bool = True
    "Sync into a mount point inside TARGET. With --no-follow-mounts: fail on one"
    ("--follow-mounts",)

    def __call__(self) -> int:
        PathSyncer(
            (lambda entry: entry.stat.st_size) if self.size_only else None,
            remove_missing=self.remove_missing,
            follow_symlinks=self.follow_symlinks,
            follow_mounts=self.follow_mounts,
            hook=self._report,
        ).sync(as_path(self.source), as_path(self.target), dry_run=self.dry_run)
        return 0

    def _report(self, source, target, event, dry_run) -> None:
        """Print one line for a change: a planned one under --dry-run, a made one under -v."""
        action = _ACTIONS.get(event)
        if action is None or not (dry_run or self.wants_detail):
            return
        prefix = "would " if dry_run else ""
        if event is SyncEvent.Copy:
            line = f"{prefix}{action} {source.path} -> {target.path}"
        else:
            line = f"{prefix}{action} {target.path}"
        text = line.encode("utf-8", "backslashreplace") + b"\n"
        copy_stream(_io.BytesIO(text), stdout())
