"""What the commands share: the base class and the standard streams."""

from __future__ import annotations

import sys as _sys
import typing as _ty

from duho import Cmd, LoggingArgs, UsageError, running_mode


class Command(LoggingArgs, Cmd):
    """The base of every command: `-v`, `-q` and `--loglevel`, and the logger
    they raise, `uripath`."""

    _logger_name_ = "uripath"
    # A tail after `--` would be ignored; a path that starts with `-` is
    # written `./-name`.
    _allow_passthrough_ = False

    @property
    def wants_detail(self) -> bool:
        """`-v` given more often than `-q`."""
        return self.verbose > self.quiet


def stdout() -> "_ty.BinaryIO":
    """The binary standard output of the process."""
    return _sys.stdout.buffer


def stdin() -> "_ty.BinaryIO":
    """The binary standard input of the process. A command served as a tool
    has none: the server reads its requests from it."""
    if running_mode() == "mcp":
        raise UsageError("standard input is not available to a tool: name a file")
    return _sys.stdin.buffer


def source_of(text: str) -> "_ty.Union[str, _ty.BinaryIO]":
    """Where a command reads bytes from: `-` is standard input, anything else
    the path or URI it names."""
    return stdin() if text == "-" else text


def target_of(text: str) -> "_ty.Union[str, _ty.BinaryIO]":
    """Where a command writes bytes to: `-` is standard output, anything else
    the path or URI it names."""
    return stdout() if text == "-" else text
