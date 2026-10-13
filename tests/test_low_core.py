"""Regressions for low-severity soundness defects in the core `Path`
protocols, `MemPath`, `FileStat`, checksums and the URI core."""

from __future__ import annotations

import errno
import hashlib
import inspect
import io
import os
import pathlib
import sys
import threading
import types

import pytest

from pathlib_next import LocalPath
from pathlib_next.mempath import MemPath, MemPathBackend
from pathlib_next.protocols import BinaryOpen
from uripath import Uri, UriPath
from uripath.schemes.data import DataUri
from uripath.schemes.file import FileUri
from uripath.source import Source
from pathlib_next import checksum
from pathlib_next import FileStat

# --- open(): handle cleanup, mode validation, line buffering ----------------


class _RecordingMemPath(MemPath):
    __slots__ = ()
    handles: list = []

    def _open(self, mode="r", buffering=-1):
        handle = super()._open(mode, buffering)
        _RecordingMemPath.handles.append(handle)
        return handle


# --- synthesized OSErrors carry errno and filename ---------------------------


def _raised(call):
    with pytest.raises(OSError) as info:
        call()
    return info.value


# --- copy(progress=) on an empty file ---------------------------------------


# --- samefile() keeps the backend / host of a str argument ------------------


class _IdentityMemPath(MemPath):
    """A MemPath whose stat() reports a (st_dev, st_ino) identity."""

    __slots__ = ()

    def stat(self, *, follow_symlinks=True):
        parent, name = self._parent_container()
        if name not in parent:
            raise FileNotFoundError(errno.ENOENT, "missing", str(self))
        return types.SimpleNamespace(
            st_mode=0o100644, st_dev=id(self.backend), st_ino=id(parent[name])
        )


def test_uripath_samefile_str_keeps_the_host(monkeypatch):
    seen = []

    def fake_stat(self, *, follow_symlinks=True):
        seen.append((self.source.host, self.path))
        return types.SimpleNamespace(st_mode=0o100644, st_dev=1, st_ino=self.path)

    monkeypatch.setattr(FileUri, "stat", fake_stat)
    path = UriPath("file://server/share/a")
    assert path.samefile("/share/a") is True
    assert seen == [("server", "/share/a"), ("server", "/share/a")]


# --- MemPath file handles behave like real files ----------------------------


def _race(action, trials=200):
    """Run `action(i)` on two threads at once per trial; return how many
    trials let both succeed."""
    both = 0
    interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for trial in range(trials):
            barrier = threading.Barrier(2)
            results = []

            def worker():
                barrier.wait()
                try:
                    action(trial)
                    results.append(True)
                except FileExistsError:
                    results.append(False)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            assert sorted(results) in ([False, True], [True, True])
            both += results == [True, True]
    finally:
        sys.setswitchinterval(interval)
    return both


# --- FileStat.from_stat with None fields ------------------------------------


# --- checksums do not claim a security use ----------------------------------


# --- is_dir()/is_file() accept follow_symlinks= (3.13 parity) ---------------


# --- pure-path gaps: str / path, 3.14 trailing-dot suffixes -----------------


def test_str_rtruediv_uri_is_a_decoded_path():
    joined = "a" / Uri("b")
    assert type(joined) is Uri
    assert joined.path == "a/b"
    # Not URI syntax: no scheme, query or fragment is parsed out of the str.
    odd = "C:/x?y#z" / Uri("b")
    assert (odd.source, odd.path, odd.query, odd.fragment) == (
        Source(None, None, None, None),
        "C:/x?y#z/b",
        "",
        "",
    )


def test_str_rtruediv_uripath_keeps_source_and_backend():
    backend = object()
    base = UriPath("http://h/b").with_backend(backend)
    joined = "a" / base
    assert type(joined) is type(base)
    # An absolute path restarts the join, as in pathlib.
    assert joined.as_uri() == "http://h/b"
    assert joined.backend is backend
    relative = "C:/p" / UriPath("x")
    assert (type(relative), relative.source, relative.path) == (
        UriPath,
        Source(None, None, None, None),
        "C:/p/x",
    )


_SUFFIX_NAMES = [
    "a",
    "a.b",
    "a.b.c",
    "a.",
    "a..",
    "..a",
    ".a.",
    "...",
    "a.b.",
    "a..b",
    ".a",
    ".a.b",
    "a.b..",
    "..a.b",
]


@pytest.mark.parametrize("name", _SUFFIX_NAMES)
def test_suffix_rules_follow_running_pathlib(name):
    expected = pathlib.PurePosixPath("x", name)
    for path in (MemPath("x", name), Uri(f"x/{name}"), UriPath(f"http://h/x/{name}")):
        assert path.name == expected.name
        assert path.suffix == expected.suffix, path
        assert path.suffixes == expected.suffixes, path
        assert path.stem == expected.stem, path
        assert path.with_suffix(".t").name == expected.with_suffix(".t").name, path


# --- explicit schemesmap is authoritative -----------------------------------


def test_explicit_schemesmap_is_not_extended_on_a_miss():
    assert type(UriPath("ftp://h/a", schemesmap={"data": DataUri})) is UriPath
    assert type(UriPath("file:///etc/x", schemesmap={"data": DataUri})) is UriPath
    assert type(UriPath("data:,x", schemesmap={"data": DataUri})) is DataUri
    assert type(UriPath("data:,x", schemesmap={})) is UriPath
    # Without a map, the registry (and lazy loading) still applies.
    assert type(UriPath("data:,x")) is DataUri


# --- lazy parse publishes a fully-initialised Uri ---------------------------


def test_lazy_parse_sets_initiated_after_the_components():
    observed = []

    class Probe(Uri):
        __slots__ = ()

        def __setattr__(self, name, value):
            if name in ("_source", "_path", "_query", "_fragment"):
                observed.append((name, bool(getattr(self, "_initiated", None))))
            object.__setattr__(self, name, value)

    probe = Probe("http://h/a?q#f")
    observed.clear()
    assert probe.path == "/a"
    assert [name for name, _ in observed] == ["_source", "_path", "_query", "_fragment"]
    assert not any(initiated for _, initiated in observed)


# --- Uri equality and hashing -----------------------------------------------


def test_uri_eq_against_relative_localpath_does_not_raise():
    assert (LocalPath("a") in [Uri("x")]) is False
    assert (Uri("x") == LocalPath("a")) is False


def test_uri_eq_is_consistent_with_hash():
    mem = MemPath("/a")
    uri = Uri("mempath:/a")
    assert uri != mem and mem != uri
    assert len({uri, mem}) == 2
    assert uri == "mempath:/a" and hash(uri) == hash("mempath:/a")
    other = UriPath("mempath:/a")
    assert uri == other and hash(uri) == hash(other)


# --- with_source() without a scheme; `/` does not mask internal errors ------


def test_with_source_without_scheme_gives_plain_uripath():
    moved = UriPath("http://h/a").with_source(Source(None, None, "other", None))
    assert type(moved) is UriPath
    assert (moved.source.host, moved.path) == ("other", "/a")


def test_truediv_does_not_mask_a_scheme_type_error(monkeypatch):
    base = UriPath("data:,a")

    def broken_init(self, *args, **kwargs):
        raise TypeError("scheme bug")

    monkeypatch.setattr(DataUri, "_init", broken_init)
    with pytest.raises(TypeError, match="scheme bug"):
        base / "b"


def test_truediv_unsupported_operand_still_returns_notimplemented():
    base = UriPath("http://h/a")
    assert base.__truediv__(3) is NotImplemented
    with pytest.raises(TypeError, match="unsupported operand"):
        base / 3
    assert (base / pathlib.PurePosixPath("b")).path == "/a/b"


# --- paths starting with "//" -----------------------------------------------


def test_posix_double_slash_path_is_not_an_authority():
    uri = Uri(pathlib.PurePosixPath("//a/b"))
    assert not uri.source
    assert uri.path == "//a/b"
    assert Uri(str(uri)).path == "//a/b"


def test_file_uri_with_empty_authority_and_double_slash_path_renders():
    uri = Uri("file:////server/share/x")
    text = str(uri)
    reparsed = Uri(text)
    assert (reparsed.source.scheme, reparsed.path) == ("file", "//server/share/x")
    assert reparsed == uri and hash(reparsed) == hash(uri)
    assert repr(uri)


# --- internationalized host names -------------------------------------------


def test_non_ascii_host_is_composed_as_idna():
    path = UriPath("http://b\u00fccher.example/a")
    assert path.source.host == "b\u00fccher.example"
    assert path.as_uri() == "http://xn--bcher-kva.example/a"
    assert UriPath(path.as_uri()) == path


def test_non_ascii_host_request_url_is_idna():
    requests = pytest.importorskip("requests")
    url = UriPath("https://b\u00fccher.example/a").as_uri()
    prepared = requests.Request("GET", url).prepare()
    assert prepared.url == "https://xn--bcher-kva.example/a"


def test_invalid_idna_host_keeps_percent_encoding():
    # An empty label cannot be IDNA-encoded.
    assert Uri("http://b\u00fc..x/a").as_uri() == "http://b%C3%BC..x/a"


# --- data: URIs -------------------------------------------------------------


@pytest.mark.parametrize("mode", ["r+b", "w", "ab", "x"])
def test_data_uri_rejects_every_writable_mode(mode):
    with pytest.raises(NotImplementedError):
        UriPath("data:,abc").open(mode)


def test_data_uri_read_handle_is_not_writable():
    with UriPath("data:,abc").open("rb") as handle:
        assert handle.writable() is False
        with pytest.raises(io.UnsupportedOperation):
            handle.write(b"zz")
        assert handle.read() == b"abc"


@pytest.mark.parametrize(
    "uri, mediatype, content",
    [
        ("data:;charset=utf-8,x", "text/plain;charset=utf-8", b"x"),
        ("data:;base64,YWJj", "text/plain;charset=US-ASCII", b"abc"),
        ("data:;charset=utf-8;base64,YWJj", "text/plain;charset=utf-8", b"abc"),
        ("data:image/png;base64,YWJj", "image/png", b"abc"),
        # No ";": "base64" is the (malformed) media type, not the encoding.
        ("data:base64,YWJj", "base64", b"YWJj"),
    ],
)
def test_data_uri_mediatype_and_base64_follow_rfc2397(uri, mediatype, content):
    path = UriPath(uri)
    assert path.mediatype == mediatype
    assert path.read_bytes() == content


# --- is_absolute() ----------------------------------------------------------


def test_uri_is_absolute_follows_the_path():
    assert Uri("/a").is_absolute() is True
    assert Uri("a").is_absolute() is False
    assert Uri("").is_absolute() is False
    assert Uri("http://h/a").is_absolute() is True
    assert UriPath("data:,abc").is_absolute() is False


def test_file_uri_of_absolute_local_path_is_absolute(tmp_path):
    uri = UriPath(LocalPath(tmp_path))
    assert isinstance(uri, FileUri)
    assert uri.is_absolute() is True


@pytest.mark.skipif(os.name != "nt", reason="drive letters are Windows-only")
def test_file_uri_drive_relative_is_not_absolute():
    assert FileUri("file:///C:/x").is_absolute() is True
    assert FileUri("file:///C:/").is_absolute() is True
    assert FileUri("file:C:").is_absolute() is False
