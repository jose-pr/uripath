"""Regression lock-in for currently-correct behavior (safety net).

These are the snippets from README.md's Quick start and examples that don't
touch the network, and the import contract: `import uripath` loads no scheme
backend and no client library.
"""

import subprocess
import sys
import textwrap

import pytest

import pathlib_next
from pathlib_next import Path, glob
from pathlib_next.mempath import MemPath


def _uri():
    """The `uripath` module."""
    import uripath

    return uripath


def _run_python(code: str) -> str:
    """Run `code` in a fresh interpreter (clean `sys.modules`), return stdout."""
    code = textwrap.dedent(code)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_import_does_not_load_netimps_or_unrelated_backends():
    _uri()
    out = _run_python("""
        import sys
        import pathlib_next
        from uripath import URIPath

        print(sorted(m for m in ("netimps", "requests", "botocore") if m in sys.modules))
        URIPath("file:/x")
        URIPath("data:,x")
        print(sorted(m for m in ("requests", "botocore") if m in sys.modules))
        """)
    assert out.split("\n")[:2] == ["[]", "[]"]


def test_import_optional_submodules_guarded():
    # Every scheme with an optional dependency is resolved lazily by
    # schemes/__init__.py; importing the package must not require
    # requests/paramiko to be installed.
    _uri()
    import uripath.schemes  # noqa: F401


def test_readme_http_path_construct_only():
    uri = _uri()
    http_path = uri.URIPath("http://example.com/data.txt")
    assert http_path.source.scheme == "http"


def test_example_uri_child_join():
    uri = _uri()
    rootless = uri.URI("sftp://root@sftpexample")
    rootless.source
    authkeys = rootless / "root/.ssh/authorized_keys"
    keys = authkeys.as_uri()
    assert keys == "sftp://root@sftpexample/root/.ssh/authorized_keys"


def test_example_query():
    uri = _uri()
    query = uri.Query({"test": "://$#!1", "test2&": [1, 2]})
    assert str(query) == "test=://$%23!1&test2%26=1&test2%26=2"
    q2 = uri.Query.parse(str(query)).to_dict()
    assert q2 == {"test": ["://$#!1"], "test2&": ["1", "2"]}
    assert query.to_pairs() == [("test", "://$#!1"), ("test2&", "1"), ("test2&", "2")]


def test_example_source():
    uri = _uri()
    src = uri.Source(scheme="scheme", userinfo="user", host="123.com", port=0)
    assert {**src} == {
        "scheme": "scheme",
        "userinfo": "user",
        "host": "123.com",
        "port": 0,
    }
    assert [*src] == ["scheme", "user", "123.com", 0]


def test_example_uripath_norm():
    URIPath = _uri().URIPath
    dest = URIPath("file:./_ssh")
    with_dots = URIPath("a/b/c/d/../../test/.")
    assert with_dots.normalized_path == "a/b/test"

    source_host = URIPath("file://test.com/path1/path2/path3/path4")
    rel_to = source_host.relative_to("/path1/path2")
    assert rel_to.as_posix() == "path3/path4"
    dest = URIPath(dest)
    assert str(URIPath("file:") / "test") == "file:test"
    assert str(URIPath()) == ""
    assert dest.as_uri() == "file:_ssh"

    test1 = dest / "test" / "test2/"
    assert str(test1) == "file:_ssh/test/test2/"


def test_example_glob_local(tmp_path):
    URIPath = _uri().URIPath
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    glob_test = URIPath(f"file:{tmp_path.as_posix()}/**/*.py")
    found = list(glob.glob(glob_test, recursive=True))
    assert len(found) == 2
