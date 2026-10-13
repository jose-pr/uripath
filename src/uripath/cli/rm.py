"""`uripath rm`: remove a path."""

from __future__ import annotations

from .. import as_path
from ._common import Command

__all__ = ["Rm"]


class Rm(Command):
    """Remove a file, an empty directory or a URI; with --recursive, a directory and everything in it."""

    _parsername_ = "rm"

    path: str
    "The file, empty directory or URI to remove. Required"
    ("path",)

    recursive: bool = False
    "Remove a directory with everything in it. Omitted: a directory must be empty"
    ("--recursive", "-r")

    missing_ok: bool = False
    "Succeed when the path does not exist. Omitted: a missing path fails"
    ("--missing-ok",)

    ignore_error: bool = False
    "Keep removing after a failure. Omitted: stop at the first"
    ("--ignore-error",)

    def __call__(self) -> int:
        as_path(self.path).rm(
            recursive=self.recursive,
            missing_ok=self.missing_ok,
            ignore_error=self.ignore_error,
        )
        return 0
