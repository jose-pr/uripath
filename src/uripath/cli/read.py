"""`uripath read`: the bytes of a path to standard output."""

from __future__ import annotations

from .. import copy_stream
from ._common import Command, source_of, stdout

__all__ = ["Read"]


class Read(Command):
    """Write the bytes of a path or URI to standard output, in chunks."""

    _parsername_ = "read"

    path: str
    "The file or URI to read; - reads standard input. Required"
    ("path",)

    def __call__(self) -> int:
        copy_stream(source_of(self.path), stdout())
        return 0
