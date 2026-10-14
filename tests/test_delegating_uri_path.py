"""`uripath.schemes.DelegatingURIPath`: a scheme whose I/O is done by a
`pathlib_next.Path` that needs no URI."""

from __future__ import annotations

import pytest

from pathlib_next import MemPath
from pathlib_next.mempath import MemPathBackend

import uripath.schemes
from uripath import URIPath
from uripath.schemes import DelegatingURIPath

STORE = MemPathBackend()
MADE: list = []


class DelegatedMemURIPath(DelegatingURIPath):
    __SCHEMES = ("delegatedmem",)
    __slots__ = ()
    _DELEGATED = ("_scandir", "_listdir", "_open", "_mkdir", "unlink", "rmdir")

    def _make_core(self):
        MADE.append(self.path)
        return MemPath(self.path or "/", backend=STORE)


class KeepsCoreNamesURIPath(DelegatedMemURIPath):
    __SCHEMES = ("delegatedkeep",)
    __slots__ = ()
    _RELABEL = False


@pytest.fixture(autouse=True)
def _empty_store():
    STORE.clear()
    MADE.clear()
    yield
    STORE.clear()


def test_the_base_is_public_and_the_built_in_delegating_schemes_use_it():
    assert "DelegatingURIPath" in uripath.schemes.__all__
    assert issubclass(DelegatingURIPath, URIPath)
    assert issubclass(URIPath.scheme_class("ftp"), DelegatingURIPath)
    assert issubclass(URIPath.scheme_class("file"), DelegatingURIPath)


def test_a_scheme_is_dispatched_to_its_class_and_does_its_io_on_the_core_path():
    root = URIPath("delegatedmem://h/")
    assert type(root) is DelegatedMemURIPath
    (root / "dir").mkdir()
    (root / "dir" / "a.txt").write_bytes(b"abc")

    assert MemPath("/dir/a.txt", backend=STORE).read_bytes() == b"abc"
    assert (root / "dir" / "a.txt").read_text() == "abc"
    assert sorted(child.name for child in (root / "dir").iterdir()) == ["a.txt"]

    (root / "dir" / "a.txt").unlink()
    (root / "dir").rmdir()
    assert list(root.iterdir()) == []


def test_a_hook_the_scheme_does_not_name_stays_unimplemented():
    path = URIPath("delegatedmem://h/x")
    with pytest.raises(NotImplementedError):
        path.chmod(0o644)


def test_the_core_path_is_made_once_per_instance_and_not_for_a_join():
    path = URIPath("delegatedmem://h/a")
    joined = path / "b"
    assert MADE == []

    (path / "..").exists()
    path.exists()
    path.exists()
    path.is_dir()
    assert MADE.count("/a") == 1
    assert joined._core is None


def test_an_error_of_the_core_path_names_the_uri_and_not_the_core_path():
    path = URIPath("delegatedmem://h/missing")
    with pytest.raises(FileNotFoundError) as raised:
        path.read_bytes()
    assert raised.value.filename == str(path)
    assert "/missing" not in [raised.value.filename]


def test_a_scheme_can_keep_the_names_the_core_path_raises_with():
    path = URIPath("delegatedkeep://h/missing")
    with pytest.raises(FileNotFoundError) as raised:
        path.read_bytes()
    assert raised.value.filename == "/missing"


def test_delegated_extra_pairs_rename_the_text_of_a_hand_written_call():
    path = URIPath("delegatedmem://h/a")
    with pytest.raises(FileNotFoundError) as raised:
        with path._delegated(("/elsewhere", "delegatedmem://h/elsewhere")):
            raise FileNotFoundError(2, "No such file or directory", "/elsewhere")
    assert raised.value.filename == "delegatedmem://h/elsewhere"
