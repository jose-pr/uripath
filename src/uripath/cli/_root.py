"""The root command and the run around it: exceptions become statuses."""

from __future__ import annotations

import sys as _sys
import typing as _ty

from duho import AUTO, Cli, DefaultsFormatter
from duho import main as _main

from .cp import Cp
from .read import Read
from .rm import Rm
from .sync import Sync
from .write import Write

#: The status of Ctrl-C (128 + 2).
_EXIT_INTERRUPTED = 130


class Uripath(Cli):
    """Read, write, copy, remove and sync local paths and URIs. A PATH is a local path or a URI; - is standard input or output where bytes are read or written."""

    _parsername_ = "uripath"
    _version_ = AUTO
    _distribution_ = "pathapi-uri"
    _help_formatter_ = DefaultsFormatter
    _exit_codes_ = {
        1: "the operation failed",
        2: "the invocation was wrong",
        130: "interrupted",
    }
    _subcommands_ = [Read, Write, Rm, Cp, Sync]


def run(argv: "_ty.Optional[_ty.Sequence[str]]") -> int:
    """Parse `argv`, run the command it names and return its exit status."""
    try:
        status = _main(Uripath, None if argv is None else list(argv))
    except SystemExit as stop:
        # The parser exits through SystemExit: 0 after --help and --version,
        # 2 on a usage error.
        if stop.code is None:
            return 0
        return stop.code if isinstance(stop.code, int) else 2
    except KeyboardInterrupt:
        return _EXIT_INTERRUPTED
    except Exception as error:
        print(f"uripath: {type(error).__name__}: {error}", file=_sys.stderr)
        return 1
    return 0 if status is None else int(status)
