"""Glob edge cases, each compared with the `pathlib` of the RUNNING
interpreter over the same tree (`LocalPath`, and a `MemPath` copy where the
rule is not about the local system), plus what `pathlib` does not answer:
listings per directory, `on_error`, audit events and loop bounds."""

import collections
import fnmatch
import itertools
import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

import pathlib_next
import uripath
from pathlib_next.mempath import MemPath
from pathlib_next import NonRelativePatternError
from pathlib_next import glob as _glob
from pathlib_next.glob import _recursion, _selection
from pathlib_next import FileStat

WINDOWS = os.name == "nt"

_FILES = (
    "a.txt",
    "b.py",
    "B2.PY",
    ".hidden.txt",
    ".hdir/inner.py",
    "sub/c.py",
    "sub/.dot.py",
    "sub/nested/d.py",
    "sub/nested/deep/e.py",
    "sub2/sub/c.py",
)
_DIRS = ("empty_dir",)


def _build(root: pathlib.Path):
    for rel in _FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
    for rel in _DIRS:
        (root / rel).mkdir()


def _mem_twin(root: pathlib.Path) -> MemPath:
    twin = MemPath("/tree")
    twin.mkdir()
    for rel in _FILES:
        target = twin / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rel)
    for rel in _DIRS:
        (twin / rel).mkdir()
    return twin


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    _build(root)
    return root


def _relative(path, base) -> str:
    text, prefix = path.as_posix(), base.as_posix()
    assert text.startswith(prefix), (text, prefix)
    return text[len(prefix) :].lstrip("/") or "."


def _answer(base, method, pattern, kwargs):
    """What a call selects, as the paths relative to `base`, or what it
    raised (a `NonRelativePatternError` is the `NotImplementedError` that
    pathlib raises)."""
    try:
        return "ok", {
            _relative(p, base) for p in getattr(base, method)(pattern, **kwargs)
        }
    except Exception as error:  # noqa: BLE001
        if isinstance(error, NotImplementedError):
            return "raised", "NotImplementedError"
        return "raised", type(error).__name__


def _compare(tree, impl_base, method, pattern, **kwargs):
    oracle = _answer(tree, method, pattern, kwargs)
    assert _answer(impl_base, method, pattern, kwargs) == oracle, (
        method,
        pattern,
        kwargs,
    )


# --- the anchor of an extended-length path is a prefix, not a wildcard ------


# --- an explicit case_sensitive changes the case rule and nothing else ------

_CASE_PATTERNS = [
    ("..", True),
    ("../*", True),
    ("*/..", True),
    ("sub/../*", True),
    ("sub/nested/..", True),
    ("**/..", True),
    ("a.txt", True),
    ("A.TXT", True),
    ("A.TXT", False),
    ("SUB", False),
    ("Sub/*.PY", False),
    (" ", False),
    ("nul", False),
]


# --- bound_loops needs a real identity --------------------------------------


class _Status:
    def __init__(self, stat, dev, ino):
        self._stat = stat
        self.st_dev, self.st_ino = dev, ino
        self.st_mode, self.st_size, self.st_mtime = (
            stat.st_mode,
            stat.st_size,
            stat.st_mtime,
        )

    def __getattr__(self, name):
        return getattr(self._stat, name)


def _identified(dev, ino):
    class Identified(MemPath):
        __slots__ = ()

        def stat(self, *, follow_symlinks=True):
            return _Status(super().stat(follow_symlinks=follow_symlinks), dev, ino)

    return Identified


# --- a literal component is checked as the running pathlib checks it --------

_LITERAL_PATTERNS = [
    "a.txt/..",
    "sub/c.py/..",
    "nonexistent/..",
    "nonexistent/*",
    "**/deep/..",
    "**/nonexistent/..",
    "sub/nested/..",
    "sub/nested/../*",
    "sub/../*",
    "../*",
    "a.txt/**",
]


# --- rglob(".") is every entry below, as pathlib's is -----------------------


# --- the last literal is tested as the running pathlib tests it -------------


@pytest.fixture
def links(tree):
    try:
        os.symlink(tree / "gone", tree / "dangling")
        os.symlink(tree / "gone_dir", tree / "dangling_dir", True)
        os.symlink(tree / "a.txt", tree / "link_file")
        os.symlink(tree / "sub", tree / "link_dir", True)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks cannot be created here")
    return tree


# --- an unlistable base is reported, whatever the first component is --------


def _reported(base, method, pattern):
    seen = []
    list(getattr(base, method)(pattern, on_error=seen.append))
    return [type(error) for error in seen]


# --- a recursive glob lists each directory once -----------------------------


class _Listed(MemPath):
    calls = collections.Counter()

    def _scandir(self):
        type(self).calls[self.as_posix()] += 1
        return super()._scandir()


class _Unreadable(_Listed):
    def _scandir(self):
        type(self).calls[self.as_posix()] += 1
        if self.name == "locked":
            raise PermissionError(13, "denied", str(self))
        return MemPath._scandir(self)


def _listed_tree(cls):
    cls.calls = collections.Counter()
    root = cls("/r")
    root.mkdir()
    for directory in ("a", "a/b", "c", "locked"):
        (root / directory).mkdir()
        (root / directory / "f.txt").write_text("x")
    (root / "top.txt").write_text("x")
    return root


# --- two "**" reach a path along several splits; it is yielded once ---------


# --- a carried pattern is validated when it is carried ----------------------


# --- the audit events pathlib raises ----------------------------------------

_AUDIT_SCRIPT = """
import json, os, pathlib, sys
events = []
sys.addaudithook(
    lambda event, args: events.append([event, *map(str, args)])
    if event.startswith("pathlib.Path.") else None
)
root = sys.argv[1]
sys.path.insert(0, sys.argv[2])
from pathlib_next import LocalPath
calls = [
    ("glob", "*.py"), ("rglob", "*.py"), ("glob", "**/*"), ("glob", ""),
    ("rglob", ""), ("glob", "/x"), ("rglob", "sub/*"), ("glob", "sub/"),
]
out = {}
for cls in (pathlib.Path, LocalPath):
    for method, pattern in calls:
        events.clear()
        try:
            list(getattr(cls(root), method)(pattern))
        except Exception:
            pass
        out.setdefault(f"{method}({pattern!r})", []).append(
            [[e[0], os.path.normpath(e[1]), *e[2:]] for e in events]
        )
print(json.dumps(out))
"""


# --- a literal on a case-insensitive listing (3.12 selects it from the listing)


class _Folding(MemPath):
    """A `MemPath` whose names are compared without regard to case."""

    __slots__ = ()

    @property
    def _is_case_sensitive(self):
        return False


def _folding_tree():
    root = _Folding("/tree")
    root.mkdir()
    (root / "sub" / "nested").mkdir(parents=True)
    (root / "sub" / "nested" / "d.py").write_text("d")
    (root / "a.txt").write_text("a")
    return root


def _found(root, pattern, **kwargs):
    return sorted(_relative(p, root) for p in root.glob(pattern, **kwargs))


# --- recurse_symlinks=True: "**" descends through symlinks to directories ---


def _symlink(target, link, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks cannot be created here")


@pytest.fixture
def linked(tmp_path):
    """A tree with links to a directory, to a link, to a file and to nothing."""
    top = tmp_path / "linked"
    (top / "real" / "deep").mkdir(parents=True)
    (top / "real" / "f.txt").write_text("f")
    (top / "real" / "deep" / "g.txt").write_text("g")
    (top / "plain").mkdir()
    (top / "plain" / "p.txt").write_text("p")
    _symlink(top / "real", top / "to_real", True)
    _symlink(top / "to_real", top / "chained", True)
    _symlink(top / "real" / "f.txt", top / "alias.txt")
    _symlink(top / "nowhere", top / "dangling")
    return top


def _walked(top, pattern):
    """What `**/<pattern>` selects, by walking with links followed."""
    found = set()
    for directory, names, files in os.walk(top, followlinks=True):
        for name in names + files:
            if fnmatch.fnmatchcase(name, pattern):
                found.add(_relative(pathlib.Path(directory, name), top))
    return found


_LINKED_IMPLS = {
    "LocalPath": lambda top: pathlib_next.LocalPath(top),
    "FileUri": lambda top: uripath.UriPath(top.as_uri()),
}


@pytest.fixture(params=sorted(_LINKED_IMPLS))
def linked_impl(request, linked):
    if request.param == "FileUri":
        pytest.importorskip("uritools")
    return _LINKED_IMPLS[request.param](linked)


@pytest.mark.parametrize("pattern", ["*.txt", "*", "g.txt", "d*"])
def test_recursing_through_symlinks_reaches_what_a_walk_with_links_reaches(
    linked, linked_impl, pattern
):
    found = {
        _relative(p, linked_impl)
        for p in linked_impl.glob(f"**/{pattern}", recurse_symlinks=True)
    }
    assert found == _walked(linked, pattern)
    assert "to_real/deep/g.txt" in _walked(linked, "g.txt")


def test_not_recursing_through_symlinks_stays_out_of_them(linked, linked_impl):
    found = {_relative(p, linked_impl) for p in linked_impl.glob("**/*.txt")}
    assert "to_real/f.txt" not in found
    assert {"real/f.txt", "alias.txt", "plain/p.txt"} <= found
    assert found == {
        _relative(p, linked_impl)
        for p in linked_impl.glob("**/*.txt", recurse_symlinks=False)
    }


@pytest.fixture
def looped(tmp_path):
    top = tmp_path / "looped"
    (top / "a" / "b").mkdir(parents=True)
    (top / "a" / "f.txt").write_text("f")
    (top / "a" / "b" / "h.txt").write_text("h")
    _symlink(top, top / "a" / "to_top", True)
    _symlink(top / "a", top / "a" / "b" / "up", True)
    _symlink(top / "a" / "b", top / "a" / "sibling", True)
    return top


# What a bounded walk may produce at most: a test that fails on a regression
# instead of hanging on it.
_LOOP_BOUND = 5000


class _Ring(MemPath):
    """A `MemPath` whose directories each hold a link `loop` to their own
    parent, with a stat that has no identity to tell the loop by."""

    __slots__ = ()

    def _is_loop(self):
        return self.name == "loop"

    def stat(self, *, follow_symlinks=True):
        if self._is_loop():
            if not follow_symlinks:
                return FileStat(stat.S_IFLNK | 0o777)
            return self.parent.stat()
        return super().stat(follow_symlinks=follow_symlinks)

    def _scandir(self):
        if self._is_loop():
            yield from self.parent._scandir()
            return
        yield from super()._scandir()
        yield "loop", FileStat(stat.S_IFLNK | 0o777)
