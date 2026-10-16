"""A scheme that no class registered.

A path of it builds, joins, compares and prints like any other, and the first
operation that needs a server raises an `ImportError` that suggests names to
look for; the name of no distribution is known. Its `Source` shows no
userinfo, since the user name may be a token.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

import uripath
from uripath import Source, URI, URIPath, UnsupportedSchemeError
from uripath.schemes import _unregistered

_SRC = pathlib.Path(uripath.__file__).resolve().parent.parent

_GROUP = (
    "the entry-point group 'uripath.schemes'. Names to look for, not known packages: "
)


def _hint(name):
    return (
        f"a distribution that provides it registers a class in {_GROUP}"
        f'pip install "{name}path[uri]", uripath-{name}, {name}uripath'
    )


#: scheme -> (a URL with a password, the message of an operation on it)
CASES = {
    "sftp": (
        "sftp://user:s3cr3t@host/dir/file.txt",
        "no class is registered for the URI scheme 'sftp'; " + _hint("sftp"),
    ),
    "svn+https": (
        "svn+https://user:s3cr3t@host/dir/file.txt",
        "no class is registered for the URI scheme 'svn+https'; " + _hint("svn"),
    ),
    "zzinvented": (
        "zzinvented://s3cr3t@host/dir/file.txt",
        "no class is registered for the URI scheme 'zzinvented'; "
        + _hint("zzinvented"),
    ),
}

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
def test_a_path_of_an_unregistered_scheme_builds_joins_compares_and_prints(scheme):
    url = CASES[scheme][0]
    path = URIPath(url)
    assert type(path) is _unregistered.UnregisteredURIPath
    assert path.source.scheme == scheme
    assert path.name == "file.txt"
    child = path.parent / "other.txt"
    assert child.parent == path.parent
    assert child.name == "other.txt"
    assert path == URIPath(url) and hash(path) == hash(URIPath(url))
    assert path != child
    assert "s3cr3t" not in str(path) and "s3cr3t" not in repr(path)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("scheme", CASES)
def test_an_operation_that_needs_the_server_names_what_to_look_for(scheme, operation):
    url, message = CASES[scheme]
    with pytest.raises(ImportError) as raised:
        OPERATIONS[operation](URIPath(url))
    assert str(raised.value) == message
    assert "s3cr3t" not in str(raised.value)


@pytest.mark.parametrize("scheme", CASES)
def test_the_scheme_class_of_an_unregistered_scheme_suggests_names_to_look_for(scheme):
    name = scheme.split("+")[0]
    with pytest.raises(UnsupportedSchemeError) as raised:
        URIPath.scheme_class(scheme.upper())
    text = str(raised.value)
    assert text.startswith(
        f"no URI scheme {scheme.upper()!r} is registered; registered: "
    )
    assert text.endswith("; " + _hint(name))


@pytest.mark.parametrize("scheme", CASES)
def test_an_unregistered_scheme_is_not_listed(scheme):
    assert scheme not in URIPath.schemes()


def test_a_path_of_an_unregistered_scheme_pickles_and_copies():
    import copy
    import pickle

    path = URIPath("zzinvented://bucket/dir/file.txt")
    for twin in (
        pickle.loads(pickle.dumps(path)),
        copy.copy(path),
        copy.deepcopy(path),
    ):
        assert twin == path
        assert type(twin) is _unregistered.UnregisteredURIPath


def test_the_name_is_the_part_of_the_scheme_before_the_first_plus():
    assert 'pip install "a-bpath[uri]", uripath-a-b, a-buripath' in (
        _unregistered.suggestions("A-B+x+y")
    )


@pytest.mark.parametrize("scheme", CASES)
def test_the_source_of_an_unregistered_scheme_shows_no_userinfo(scheme):
    source = Source(scheme, "s3cr3t:pw", "host", None)
    assert str(source) == f"{scheme}://host"
    assert "s3cr3t" not in repr(source) and "pw" not in repr(source)
    assert "s3cr3t" not in str(URI(f"{scheme}://s3cr3t@host/x"))
    assert "s3cr3t" not in repr(URIPath(f"{scheme}://s3cr3t@host/x"))
    assert Source.parse(f"{scheme}://s3cr3t@host").userinfo == "s3cr3t"


def test_a_registered_scheme_keeps_the_user_name_and_drops_the_password():
    assert str(Source("ftp", "user:pw", "host", None)) == "ftp://user@host"
    assert str(Source("FTP", "user:pw", "host", None)) == "ftp://user@host"
    assert str(Source(None, "user", "host", None)) == "//user@host"


def test_a_class_says_that_its_user_name_is_a_secret():
    class SecretUserinfoPath(URIPath):
        __SCHEMES = ("zzsecretuser",)
        _SECRET_USERINFO = True

    class PlainUserinfoPath(URIPath):
        __SCHEMES = ("zzplainuser",)

    assert str(Source("zzsecretuser", "tok", "host", None)) == "zzsecretuser://host"
    assert (
        str(Source("zzplainuser", "who:pw", "host", None)) == "zzplainuser://who@host"
    )
    assert "tok" not in repr(URIPath("zzsecretuser://tok@host/x"))
    assert Source("zzsecretuser", "tok", "host", None).reveal() == (
        "zzsecretuser://tok@host"
    )


def test_a_class_that_fails_to_load_hides_the_userinfo(monkeypatch):
    def fail(scheme, strict=False):
        raise RuntimeError("cannot load")

    monkeypatch.setattr(URIPath, "_find_scheme", staticmethod(fail))
    assert str(Source("ftp", "tok", "host", None)) == "ftp://host"


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
        b"from uripath import URIPath\n"
        b"class Provided(URIPath):\n"
        b"    __SCHEMES = ('sftp',)\n"
    )
    code = textwrap.dedent("""
        from uripath import URIPath
        path = URIPath("sftp://host/dir/file.txt")
        print(type(path).__name__)
        print(URIPath.scheme_class("sftp").__name__)
        print(type(URIPath("zzother://bucket/key")).__name__)
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
    assert result.stdout.splitlines() == ["Provided", "Provided", "UnregisteredURIPath"]


def test_the_stand_in_takes_the_keywords_of_the_class_that_is_missing():
    path = URIPath("zzinvented://h/x", ssh_config="x", profile="work")
    assert type(path) is _unregistered.UnregisteredURIPath
