"""Differential glob tests: `pathlib.Path.glob()`/`rglob()` of the RUNNING
interpreter is the oracle, compared as sets of relative paths over the same
real tree for LocalPath, a FileUri of it, and a MemPath copy of it.

Expected results legitimately differ by interpreter (a trailing "**" also
selects files on 3.13+), which is why nothing here hard-codes them.
"""

import os
import pathlib
import sys
import time

import pytest
from capabilities import requires_junctions

import pathlib_next
from pathlib_next.mempath import MemPath
from uripath import UriPath
from pathlib_next import glob as _glob

_FILES = (
    "a.txt",
    "b.py",
    ".h.txt",
    ".hd/e.py",
    ".hd/deep/f.txt",
    "sub/c.py",
    "sub/nested/d.py",
    "sub/nested/.hn.txt",
    "rep/rep/rep/g.py",
)
_DIRS = ("empty",)

_PATTERNS = [
    "*",
    "*.txt",
    "*.py",
    ".*",
    "?.txt",
    "[ab].*",
    "a.txt",
    "missing",
    "missing/*",
    "a.txt/*",
    "a.txt/**",
    "sub",
    "sub/",
    "sub/*",
    "*/*.py",
    "sub/nested/*",
    "**",
    "sub/**",
    "**/",
    "sub/**/",
    "**/*",
    "**/*.py",
    "**/**/*.py",
    "**/**",
    "**/rep/**/*.py",
    "rep/**/rep/**",
    "**/rep/**/rep/*",
    "**/nested/*",
    "**/.hd/**",
]
# A trailing separator selects directories only from 3.11; older pathlib
# ignored it, while pathlib_next applies it on every version.
_TRAILING_SEP_WILDCARD = ["*/", "sub/*/", "**/*/"]

_RGLOB_PATTERNS = ["*.py", "*", "rep", "nested/*", ".*", ""]


def _build(root: pathlib.Path):
    for rel in _FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel)
    for rel in _DIRS:
        (root / rel).mkdir()


def _rel(path, base) -> str:
    s, b = path.as_posix(), base.as_posix()
    assert s.startswith(b), (s, b)
    return s[len(b) :].lstrip("/") or "."


def _stdlib(root, method, pattern):
    return {_rel(p, root) for p in getattr(root, method)(pattern)}


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    _build(root)
    return root


def _mempath(root: pathlib.Path) -> MemPath:
    base = MemPath("/tree")
    base.mkdir()
    for rel in _FILES:
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rel)
    for rel in _DIRS:
        (base / rel).mkdir()
    return base


_IMPLS = {
    "LocalPath": lambda root: pathlib_next.LocalPath(root),
    "FileUri": lambda root: UriPath(root.as_uri()),
    "MemPath": _mempath,
}


@pytest.fixture(params=sorted(_IMPLS))
def impl(request, tree):
    return _IMPLS[request.param](tree)


def _ours(base, method, pattern, **kwargs):
    found = [_rel(p, base) for p in getattr(base, method)(pattern, **kwargs)]
    assert len(found) == len(set(found)), f"duplicates: {sorted(found)}"
    return set(found)


@pytest.mark.parametrize("pattern", _PATTERNS + _TRAILING_SEP_WILDCARD)
def test_glob_matches_running_pathlib(tree, impl, pattern):
    if pattern in _TRAILING_SEP_WILDCARD and sys.version_info < (3, 11):
        pytest.skip("pathlib < 3.11 ignores a trailing separator")
    assert _ours(impl, "glob", pattern) == _stdlib(tree, "glob", pattern)


@pytest.mark.parametrize("pattern", _RGLOB_PATTERNS)
def test_rglob_matches_running_pathlib(tree, impl, pattern):
    assert _ours(impl, "rglob", pattern) == _stdlib(tree, "rglob", pattern)


def test_trailing_doublestar_follows_interpreter(tree, impl):
    found = _ours(impl, "glob", "sub/**")
    assert ("sub/c.py" in found) is (sys.version_info >= (3, 13))
    assert {"sub", "sub/nested"} <= found


def test_include_hidden_false_filters_and_skips_hidden_dirs(impl):
    found = _ours(impl, "glob", "**/*", include_hidden=False)
    assert not any(part.startswith(".") for p in found for part in p.split("/"))
    assert "sub/nested/d.py" in found
    # A literal hidden component is never filtered.
    assert _ours(impl, "glob", ".hd/*", include_hidden=False) == {
        ".hd/e.py",
        ".hd/deep",
    }


def test_include_hidden_false_leaves_hidden_entries_out_of_a_final_recursive_wildcard(
    impl,
):
    found = _ours(impl, "glob", "**", include_hidden=False)
    named = {name for name in found if name not in ("", ".")}
    assert not any(part.startswith(".") for name in named for part in name.split("/"))
    assert "sub/nested" in named
    assert _ours(impl, "glob", "**", include_hidden=True) > found


def test_missing_or_file_base_selects_nothing(tree, impl):
    for base in (impl / "missing", impl / "a.txt"):
        for pattern in ("*", "**", "**/*.py", "x/*"):
            assert list(base.glob(pattern)) == []


# --- directory symlink cycles ------------------------------------------------


@pytest.fixture
def loop_tree(tmp_path):
    root = tmp_path / "loop"
    (root / "a").mkdir(parents=True)
    (root / "a" / "f.txt").write_text("f")
    try:
        # Two cycles: before the fix recursion branched 2x per level.
        os.symlink(root, root / "a" / "loop", target_is_directory=True)
        os.symlink(root, root / "a" / "loop2", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    return root


@pytest.mark.parametrize("kind", ["LocalPath", "FileUri"])
@pytest.mark.parametrize(
    "method,pattern",
    [
        ("glob", "**"),
        ("glob", "**/"),
        ("glob", "**/*"),
        ("glob", "**/f.txt"),
        ("glob", "*/loop/*"),
        ("glob", "a/*/"),
        ("rglob", "f.txt"),
        ("rglob", "*"),
    ],
)
def test_glob_does_not_recurse_into_directory_symlinks(
    loop_tree, kind, method, pattern
):
    last = pattern.rstrip("/").split("/")[-1]
    if pattern.endswith("/") and last != "**" and sys.version_info < (3, 11):
        pytest.skip("pathlib < 3.11 ignores a trailing separator")
    base = _IMPLS[kind](loop_tree)
    start = time.monotonic()
    assert _ours(base, method, pattern) == _stdlib(loop_tree, method, pattern)
    assert time.monotonic() - start < 10


# --- pattern validation ------------------------------------------------------










def test_recurse_symlinks_adds_nothing_where_the_tree_has_no_links(impl):
    assert _ours(impl, "glob", "*.py", recurse_symlinks=False) == {"b.py"}
    for method, pattern in (("glob", "**"), ("glob", "**/*.py"), ("rglob", "*")):
        assert _ours(impl, method, pattern, recurse_symlinks=True) == _ours(
            impl, method, pattern
        )


def test_uripath_question_mark_is_a_wildcard(tree):
    (tree / "a1.txt").write_text("1")
    (tree / "a2.txt").write_text("2")
    base = UriPath(tree.as_uri())
    assert {p.name for p in base.glob("a?.txt")} == {"a1.txt", "a2.txt"}
    assert {p.name for p in base.glob("*/n?sted/*.py")} == {"d.py"}




# --- full_match ----------------------------------------------------------------

_FULL_MATCH_CASES = [
    ("a", "a/**", False),
    ("a/b", "a/**", True),
    ("a/b", "a/b/", True),
    ("a/b", "**", True),
    ("a", "**/a", True),
    ("a/b", "a/**/b", True),
    ("a/b", "**/**", True),
    ("a", "**/**", True),
    ("a/b/c", "a/**/**/c", True),
    ("a/b", "*", False),
    ("a/b", "*/*", True),
    ("/a/b", "/a/**", True),
    ("a/.b", "a/*", True),
    ("a/b/c", "**/c/**", False),
    ("a/b", "a/b/**", False),
    ("a/b", "**/b/", True),
]






# --- glob(None): expand the pattern this path carries ---------------------


@pytest.mark.parametrize("cls", ["local", "uri"])
def test_glob_none_expands_the_pattern_the_path_carries(tree, cls):
    """`glob("")` raises like pathlib; `glob(None)` is the supported way to
    expand a path that IS a pattern -- what yaconfiglib's `glob("")` did
    before 0.9.4."""
    root = pathlib_next.LocalPath(tree)
    carrier = root / "*.py" if cls == "local" else UriPath((root / "*.py").as_uri())
    got = sorted(p.name for p in carrier.glob(None))
    assert got == sorted(p.name for p in root.glob("*.py"))
    assert got






# --- native=: follow the interpreter, or one rule everywhere --------------












# --- on_error: an unreadable directory can be seen ------------------------


@pytest.fixture
def unreadable_tree(tmp_path, monkeypatch):
    """A tree whose `locked/` directory refuses to list, without needing
    real permissions (which a Windows admin ignores anyway)."""
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "a.json").write_text("{}")
    (tmp_path / "locked").mkdir()
    (tmp_path / "locked" / "b.json").write_text("{}")
    real = pathlib_next.LocalPath._scandir

    def refusing(self):
        if self.name == "locked":
            raise PermissionError(13, "Permission denied", str(self))
        return real(self)

    monkeypatch.setattr(pathlib_next.LocalPath, "_scandir", refusing)
    return tmp_path








# --- bound_loops: a directory is walked once per "**" ---------------------








def _junction(link, target):
    """`mklink /J` returns 0 without elevation, unlike `os.symlink`."""
    import subprocess

    subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )




