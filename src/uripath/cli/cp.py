"""`uripath cp`: copy a path, a tree or a stream."""

from __future__ import annotations

from duho import UsageError

from .. import as_path, copy_stream
from ._common import Command, source_of, target_of

__all__ = ["Cp"]


class Cp(Command):
    """Copy a file, or with --recursive a directory, from SOURCE to TARGET; either may be a URI."""

    _parsername_ = "cp"

    source: str
    "The file, directory or URI to copy; - reads standard input. Required"
    ("source",)

    target: str
    "Where to copy it to; - writes standard output. Required"
    ("target",)

    recursive: bool = False
    "Copy a directory with everything in it; not with -. Omitted: a single file"
    ("--recursive", "-r")

    overwrite: bool = False
    "Replace an existing TARGET. Omitted: an existing TARGET is refused"
    ("--overwrite",)

    follow_symlinks: bool = True
    "Copy what a symbolic link points to. With --no-follow-symlinks: copy the link itself"
    ("--follow-symlinks",)

    preserve_metadata: bool = True
    "Copy modes and times where the target can hold them. With --no-preserve-metadata: leave them out"
    ("--preserve-metadata",)

    def __call__(self) -> int:
        streamed = "-" in (self.source, self.target)
        if streamed and self.recursive:
            raise UsageError("--recursive cannot copy from or to '-'")
        if streamed:
            # An exclusive create: no check-then-write race on the target.
            copy_stream(
                source_of(self.source),
                target_of(self.target),
                exclusive=not self.overwrite,
            )
            return 0
        as_path(self.source).copy(
            as_path(self.target),
            overwrite=self.overwrite,
            follow_symlinks=self.follow_symlinks,
            preserve_metadata=self.preserve_metadata,
            recursive=self.recursive,
        )
        return 0
