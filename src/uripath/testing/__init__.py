"""The suite that holds every HTTP transport to the same promises.

`http:`, `dav:`, `github:`, `gitlab:` and `git:` are tested over a transport
chosen by name, and the transport itself against loopback servers scripted at
the byte level. A distribution that provides a transport (see
`uripath.transports`) runs the same tests over its own, with its distribution
installed::

    python -m uripath.testing --http-transports requests -q

Everything after `python -m uripath.testing` is passed to pytest, which this
module needs. `--http-transports` takes names that `uripath.transports.names()`
lists, separated by commas; it defaults to `builtin`. Every request goes to the
loopback interface: the suite fails a test that tries to reach any other host.
"""

from __future__ import annotations

import pathlib as _pathlib
import typing as _ty

__all__ = ["HELPERS", "MODULES", "run", "suite_directory"]

MODULES = (
    "test_backend_family.py",
    "test_backend_scope.py",
    "test_contract.py",
    "test_dav.py",
    "test_git_backend_sharing.py",
    "test_git_replies.py",
    "test_github_stat.py",
    "test_gitrepo.py",
    "test_http.py",
    "test_http_body.py",
    "test_http_credentials.py",
    "test_http_listing.py",
    "test_http_live.py",
    "test_http_peer_text.py",
    "test_http_redirect_origin.py",
    "test_http_redirects.py",
    "test_http_reply_limits.py",
    "test_http_transport.py",
    "test_http_writes.py",
    "test_httpdav_safety.py",
    "test_listing_hints_http.py",
    "test_low_schemes.py",
    "test_routing.py",
    "test_transport_security.py",
)
"""The test modules that run once per transport, by file name."""

HELPERS = (
    "capabilities.py",
    "census.py",
    "conftest.py",
    "hermetic.py",
    "http_fakes.py",
    "http_wire.py",
    "server_loops.py",
    "waits.py",
)
"""The files beside them that they import: the fixtures and the loopback servers."""


def suite_directory() -> _pathlib.Path:
    """The directory that holds `MODULES` and `HELPERS`: the copy installed
    with the package, or `tests/` of a source checkout. Raises
    `FileNotFoundError` when neither is there."""
    here = _pathlib.Path(__file__).resolve().parent
    for candidate in (here / "suite", here.parents[2] / "tests"):
        if all((candidate / name).is_file() for name in (*MODULES, *HELPERS)):
            return candidate
    raise FileNotFoundError("the transport suite is not installed with uripath")


def run(arguments: "_ty.Sequence[str] | None" = None) -> int:
    """Runs `MODULES` with pytest and `arguments` (pytest options, such as
    `--http-transports requests`) and returns the exit status. Raises
    `ImportError` when pytest is not installed."""
    try:
        import pytest
    except ImportError as error:
        raise ImportError(
            "the transport suite needs pytest: pip install pytest", name="pytest"
        ) from error
    directory = suite_directory()
    files = [str(directory / name) for name in MODULES]
    return int(pytest.main([*(arguments or ()), *files]))
