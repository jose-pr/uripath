"""Pure-path operations that the generic `Pathname` derives (`MemPath`, `Uri`)
against `pathlib.PurePosixPath`: `full_match()`, `with_stem()`,
`is_absolute()`, and the 3.12 pass of `match()`."""

from __future__ import annotations

import itertools
import pathlib
import re
import sys
import types

import pytest

from pathlib_next.path import _pure as path_module
from pathlib_next.mempath import MemPath
from uripath import Uri

GENERIC = [MemPath, Uri]

# --- full_match() ---------------------------------------------------------

#: `(path, pattern, expected)` as `PurePosixPath.full_match` answers on 3.14,
#: asserted on every interpreter. The root is a component of its own: a lone
#: "*" never matches it, a rooted pattern names it, and a leading "**" needs
#: a name behind it to reach it.
FULL_MATCH = [
    ("/a/b.txt", "*/*/*.txt", False),
    ("/a/b.txt", "/*/*.txt", True),
    ("/a/b.txt", "/**/*.txt", True),
    ("/a/b.txt", "**/*.txt", True),
    ("/b.txt", "**/*.txt", False),
    ("b.txt", "**/*.txt", True),
    ("/", "/**", True),
    ("/", "**", True),
    ("/", "/", True),
    ("/", "*", False),
    ("/", "/*", False),
    ("/", "**/x", False),
    ("/a", "/", False),
    ("/a", "*", False),
    ("/a", "**/a", False),
    ("/a", "**/*", False),
    ("/a", "/*", True),
    ("/a", "/**", True),
    ("/a/x", "**/x", True),
    ("/x", "**/x", False),
    ("/a", "*/*", False),
    ("/a/b", "*/*/*", False),
    ("/..", "*/*", False),
    ("/a/b", "/**/b", True),
    ("/b", "/**/b", True),
    ("a/b", "a/./b", True),
    ("a/b", "a//b", True),
    ("a/b", "./a/b", True),
    ("a/b", "a/b/", True),
    ("a/b", "a/*", True),
    ("a/b", "a/**", True),
    ("a", "a/**", False),
    ("a", "**/a/**", False),
    ("a", "**/a", True),
    ("a/b/c", "**/c", True),
    ("a/b/c", "a/**/c", True),
    ("a/c", "a/**/c", True),
    ("a/b", "*", False),
    ("", "", True),
    ("", ".", True),
    ("", "**", True),
    ("", "*", False),
    ("", "/**", False),
    ("a", "A", False),
]


@pytest.mark.parametrize("cls", GENERIC)
@pytest.mark.parametrize("path,pattern,expected", FULL_MATCH)
def test_full_match_follows_the_root_as_a_component(cls, path, pattern, expected):
    assert cls(path).full_match(pattern) is expected




def _generated_paths():
    names = ["a", "b", "c.txt"]
    for depth in range(0, 4):
        for combo in itertools.product(names, repeat=depth):
            relative = "/".join(combo)
            yield relative
            if combo:
                yield "/" + relative
    yield "/"


def _generated_patterns():
    parts = ["*", "**", "a", "c.txt", "?"]
    for depth in range(0, 4):
        for combo in itertools.product(parts, repeat=depth):
            relative = "/".join(combo)
            yield relative
            yield "/" + relative
            if combo:
                yield relative + "/"
    yield from ["./a", "a/./b", ".", "a//b"]












# --- with_stem() and is_absolute() ---------------------------------------


def _outcome(call):
    try:
        return call()
    except ValueError:
        return ValueError


@pytest.mark.parametrize("cls", [MemPath, Uri])
@pytest.mark.parametrize("name", ["c.txt", "c", "c.tar.gz", ".hidden", "c."])
@pytest.mark.parametrize("stem", ["", "d", "d.e"])
def test_with_stem_refuses_what_the_running_pathlib_refuses(cls, name, stem):
    stdlib = _outcome(lambda: pathlib.PurePosixPath("/a/" + name).with_stem(stem))
    generic = _outcome(lambda: cls("/a/" + name).with_stem(stem))
    if stdlib is ValueError:
        assert generic is ValueError
    else:
        assert generic is not ValueError
        assert generic.as_posix().endswith(stdlib.as_posix().rpartition("/")[2])








# --- the 3.12 pass of match() --------------------------------------------


def _reference_match_312(path: str, pattern: str, case_sensitive: bool = True):
    """CPython 3.12's `PurePath.match`, retyped over strings:
    `_compile_pattern_lines` on a pattern whose separators and newlines were
    swapped, matched against the path's lines."""
    import fnmatch

    swap = str.maketrans({"/": "\n", "\n": "/"})
    path_text = str(pathlib.PurePosixPath(path))
    pattern_path = pathlib.PurePosixPath(pattern)
    pattern_text = str(pattern_path)
    path_lines = "" if path_text == "." else path_text.translate(swap)
    pattern_lines = "" if pattern_text == "." else pattern_text.translate(swap)
    parts = ["^"]
    for part in pattern_lines.splitlines(keepends=True):
        if part == "*\n":
            part = r".+\n"
        elif part == "*":
            part = r".+"
        else:
            part = fnmatch.translate(part)[len("(?s:") : -len(")\\Z")]
        parts.append(part)
    parts.append(r"\Z")
    flags = re.MULTILINE | (0 if case_sensitive else re.IGNORECASE)
    compiled = re.compile("".join(parts), flags)
    if pattern_path.root:
        return compiled.match(path_lines) is not None
    if pattern_path.parts:
        return compiled.search(path_lines) is not None
    raise ValueError("empty pattern")


NEWLINE_PATHS = ["a\nb", "a/b\nc", "a\nb/c", "\n", "/a\nb", "a/b", "/a/b", "x\n/y"]
NEWLINE_PATTERNS = [
    "a/b",
    "a\nb",
    "*",
    "*/*",
    "*\n*",
    "a*",
    "?\n?",
    "[!a]",
    "b\nc",
    "**",
    "/a/b",
    "/a\nb",
    "\n",
    "c",
    "b/c",
]


@pytest.fixture
def as_python_312(monkeypatch):
    monkeypatch.setattr(
        path_module, "_sys", types.SimpleNamespace(version_info=(3, 12, 7))
    )






