"""A scheme class constructs, joins and compares with every third-party client
library hidden, and the schemes of this package need none. Each case runs in a
fresh interpreter that blocks the import (`sys.modules[name] = None`), so nothing
is uninstalled and no socket is opened: the child raises on any connect or
lookup."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

import uripath

_PRELUDE = """
import socket, sys

def _refuse(*args, **kwargs):
    raise RuntimeError("network used")

socket.socket.connect = _refuse
socket.getaddrinfo = _refuse
for name in {blocked!r}:
    sys.modules[name] = None
"""


_SRC = pathlib.Path(uripath.__file__).resolve().parent.parent


def _run(code: str, blocked=()) -> subprocess.CompletedProcess:
    script = _PRELUDE.format(blocked=tuple(blocked)) + textwrap.dedent(code)
    env = dict(os.environ)
    # The checkout under test, not whichever copy is installed.
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(_SRC), env.get("PYTHONPATH")])
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


#: URLs that need no client library: they build, join and compare with
#: `requests` hidden, and are sent by the built-in HTTP transport.
_HTTP_URLS = [
    "http://h/x",
    "https://h/x",
    "dav://h/x",
    "davs://h/x",
]


@pytest.mark.parametrize("url", _HTTP_URLS)
def test_a_path_with_the_client_libraries_hidden_does_pure_path_work(url):
    result = _run(
        f"""
        from uripath import URIPath
        path = URIPath({url!r})
        child = path / "y"
        assert child.name == "y" and child.parent == path
        assert child.as_uri().startswith({url.split("://")[0] + "://"!r})
        assert path == URIPath({url!r}) and hash(path) == hash(URIPath({url!r}))
        assert path.relative_to(path).as_posix() in ("", ".")
        assert (path.with_name("z") if path.name else path).as_uri()
        print(type(path).__name__)
        """,
        ["requests", "urllib3"],
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_schemes_that_need_no_extra_work_with_every_client_blocked():
    result = _run(
        """
        import uripath.schemes as schemes
        from uripath import URIPath

        for name in ("HTTPURIPath", "DAVURIPath", "FTPURIPath", "ZipURIPath",
                     "TarURIPath", "FileURIPath", "DataURIPath"):
            assert hasattr(schemes, name), name
        assert URIPath("data:,abc").read_bytes() == b"abc"
        print("ok")
        """,
        [
            "requests",
            "urllib3",
            "botocore",
            "boto3",
            "google.cloud.storage",
            "azure.storage.blob",
            "paramiko",
            "asyncssh",
        ],
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
