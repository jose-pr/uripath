"""Schemes and an HTTP transport that other distributions provide.

`sftp:`, `s3:`, `gs:` and `az:` and the `requests` transport are not part of
this package. Their names are known: a path of such a scheme builds, joins,
compares and prints, and the first operation that needs the server raises an
`ImportError` naming the distribution to install. An installed distribution
registers its own class and takes the name.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

import uripath
from uripath import UriPath
from uripath.schemes import _elsewhere
from uripath.schemes.gitlab import RepoBackend
from uripath.schemes.http import HttpBackend, HttpPath

_SRC = pathlib.Path(uripath.__file__).resolve().parent.parent

#: scheme -> (a URL with a password where the scheme has userinfo, the message)
CASES = {
    "sftp": (
        "sftp://user:s3cr3t@host/dir/file.txt",
        "the 'sftp' scheme is provided by the uripath-sftp distribution: "
        'pip install "uripath-sftp[paramiko]" (or "uripath-sftp[asyncssh]")',
    ),
    "s3": (
        "s3://bucket/dir/file.txt",
        "the 's3' scheme is provided by the uripath-objstore distribution: "
        'pip install "uripath-objstore[s3]"',
    ),
    "gs": (
        "gs://bucket/dir/file.txt",
        "the 'gs' scheme is provided by the uripath-objstore distribution: "
        'pip install "uripath-objstore[gs]"',
    ),
    "az": (
        "az://account/container/file.txt",
        "the 'az' scheme is provided by the uripath-objstore distribution: "
        'pip install "uripath-objstore[az]"',
    ),
}

REQUESTS_MESSAGE = (
    "the 'requests' HTTP transport is provided by the uripath-http-requests "
    "distribution: pip install uripath-http-requests"
)

#: Each is one public operation that needs the server.
OPERATIONS = {
    "stat": lambda p: p.stat(),
    "exists": lambda p: p.exists(),
    "is_dir": lambda p: p.is_dir(),
    "is_file": lambda p: p.is_file(),
    "read_bytes": lambda p: p.read_bytes(),
    "read_text": lambda p: p.read_text(),
    "open": lambda p: p.open("rb"),
    "iterdir": lambda p: list(p.iterdir()),
    "glob": lambda p: list(p.glob("*")),
    "walk": lambda p: list(p.walk()),
    "write_text": lambda p: p.write_text("x"),
    "mkdir": lambda p: p.mkdir(),
    "unlink": lambda p: p.unlink(),
    "rmdir": lambda p: p.rmdir(),
    "rename": lambda p: p.rename("other.txt"),
    "chmod": lambda p: p.chmod(0o644),
    "touch": lambda p: p.touch(),
    "copy": lambda p: p.copy("file:target.txt"),
    "rm": lambda p: p.rm(),
}


@pytest.mark.parametrize("scheme", CASES)
def test_a_path_of_a_scheme_provided_elsewhere_builds_joins_compares_and_prints(scheme):
    url = CASES[scheme][0]
    path = UriPath(url)
    assert type(path) is _elsewhere.ProvidedElsewhere
    assert path.source.scheme == scheme
    assert path.name == "file.txt"
    child = path.parent / "other.txt"
    assert child.parent == path.parent
    assert child.name == "other.txt"
    assert path == UriPath(url) and hash(path) == hash(UriPath(url))
    assert path != child
    assert "s3cr3t" not in str(path) and "s3cr3t" not in repr(path)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("scheme", CASES)
def test_an_operation_that_needs_the_server_names_what_to_install(scheme, operation):
    url, message = CASES[scheme]
    with pytest.raises(ImportError) as raised:
        OPERATIONS[operation](UriPath(url))
    assert str(raised.value) == message
    assert "s3cr3t" not in str(raised.value)


@pytest.mark.parametrize("scheme", CASES)
def test_the_scheme_class_of_a_scheme_provided_elsewhere_names_what_to_install(scheme):
    with pytest.raises(ImportError) as raised:
        UriPath.scheme_class(scheme.upper())
    assert str(raised.value) == CASES[scheme][1]


@pytest.mark.parametrize("scheme", CASES)
def test_a_scheme_provided_elsewhere_is_listed(scheme):
    assert scheme in UriPath.schemes()


def test_a_scheme_nobody_provides_is_still_a_value_error():
    with pytest.raises(ValueError, match="no URI scheme 'nosuchscheme'"):
        UriPath.scheme_class("nosuchscheme")


def test_a_path_of_a_scheme_provided_elsewhere_pickles_and_copies():
    import copy
    import pickle

    path = UriPath("s3://bucket/dir/file.txt")
    for twin in (
        pickle.loads(pickle.dumps(path)),
        copy.copy(path),
        copy.deepcopy(path),
    ):
        assert twin == path
        assert type(twin) is _elsewhere.ProvidedElsewhere


def test_an_installed_distribution_takes_the_scheme(tmp_path):
    dist = tmp_path / "elsewhere_plugin-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_bytes(
        b"Metadata-Version: 2.1\nName: elsewhere-plugin\nVersion: 1.0\n"
    )
    (dist / "entry_points.txt").write_bytes(
        b"[uripath.schemes]\nsftp = elsewhere_plugin:Provided\n"
    )
    (tmp_path / "elsewhere_plugin.py").write_bytes(
        b"from uripath import UriPath\n"
        b"class Provided(UriPath):\n"
        b"    __SCHEMES = ('sftp',)\n"
    )
    code = textwrap.dedent("""
        from uripath import UriPath
        path = UriPath("sftp://host/dir/file.txt")
        print(type(path).__name__)
        print(UriPath.scheme_class("sftp").__name__)
        print(type(UriPath("s3://bucket/key")).__name__)
        """)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_SRC), str(tmp_path), *filter(None, [env.get("PYTHONPATH")])]
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["Provided", "Provided", "ProvidedElsewhere"]


# --- the requests transport -------------------------------------------------


def test_with_session_names_the_distribution_that_provides_the_transport():
    with pytest.raises(ImportError) as raised:
        HttpPath("http://h/x").with_session(object(), write_method="POST")
    assert str(raised.value) == REQUESTS_MESSAGE
    assert raised.value.name == "uripath_http_requests"


@pytest.mark.parametrize("arguments", [{"session": object()}, {"verify": False}])
def test_a_repository_backend_given_a_session_names_the_distribution(arguments):
    with pytest.raises(ImportError) as raised:
        RepoBackend(**arguments)
    assert str(raised.value) == REQUESTS_MESSAGE


def test_the_requests_transport_asked_for_by_the_environment_names_the_distribution(
    monkeypatch,
):
    monkeypatch.setenv("PATHLIB_NEXT_HTTP_TRANSPORT", "requests")
    with HttpBackend() as backend:
        with pytest.raises(ImportError) as raised:
            backend.transport
    assert str(raised.value) == REQUESTS_MESSAGE
    # the choice is reported where a request is sent, not where a path is built
    path = UriPath("http://127.0.0.1:1/x")
    assert path.name == "x"
    with pytest.raises(ImportError, match="uripath-http-requests"):
        path.stat()
