"""The `uripath` command line, built on `duho`.

`main` is the entry point of the `uripath` console script and of `python -m
uripath`. It needs the `cli` extra (`pip install "uripath[cli]"`); importing
this package does not, so a bare install gets one line naming the extra in
place of an `ImportError`. The root command, `Uripath`, is built on first use
because its base class comes from `duho`.
"""

from __future__ import annotations

import sys as _sys
import typing as _ty

if _ty.TYPE_CHECKING:
    from ._root import Uripath

__all__ = ["main"]

_NEEDS_EXTRA = (
    'uripath: error: the command line needs the "cli" extra: '
    'pip install "uripath[cli]"'
)


def main(argv: "_ty.Optional[_ty.Sequence[str]]" = None) -> int:
    """Run one `uripath` command and return its exit status.

    `argv` is the arguments after the program name (default `sys.argv[1:]`).
    Returns 0 on success, 1 when the operation failed, 2 for a wrong
    invocation, 130 on Ctrl-C and 141 when the reader of standard output went
    away. Results go to stdout and one `uripath: <Type>: <message>` line per
    failure to stderr. Without `duho` it prints which extra to install and
    returns 1.
    """
    try:
        import duho  # noqa: F401
    except ModuleNotFoundError as error:
        if error.name != "duho":
            raise
        print(_NEEDS_EXTRA, file=_sys.stderr)
        return 1
    from ._root import run

    return run(argv)


def __getattr__(name: str) -> "_ty.Any":
    """`Uripath`, the root command, imported on first use."""
    if name == "Uripath":
        from ._root import Uripath

        return Uripath
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
