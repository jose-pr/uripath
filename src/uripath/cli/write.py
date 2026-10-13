"""`uripath write`: standard input, or the text given, into a path."""

from __future__ import annotations

import io as _io
import typing as _ty

from duho import Arg, Meta

from .. import as_path, copy_stream
from ._common import Command, stdin, stdout, target_of

__all__ = ["Write"]


def _encoding(name: str) -> str:
    """A text encoding the interpreter knows (not a bytes-to-bytes codec)."""
    try:
        "".encode(name)
    except LookupError:
        raise ValueError(f"unknown text encoding: {name!r}") from None
    return name


class Write(Command):
    """Write standard input, or the text DATA, to a path or URI, replacing what is there."""

    _parsername_ = "write"

    path: str
    "The file or URI to write, replacing it; - writes standard output. Required"
    ("path",)

    data: _ty.Optional[str] = None
    "The text to write, encoded with --encoding. Omitted: the bytes of standard input"
    ("data",)

    encoding: Arg[str, Meta(type=_encoding)] = "utf-8"
    "The text encoding of DATA"
    ("--encoding",)

    def __call__(self) -> int:
        if self.data is None:
            copy_stream(stdin(), target_of(self.path))
        elif self.path == "-":
            copy_stream(_io.BytesIO(self.data.encode(self.encoding)), stdout())
        else:
            as_path(self.path).write_bytes(self.data.encode(self.encoding))
        return 0
