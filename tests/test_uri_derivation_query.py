"""Every path-only derivation of a URI keeps its query and fragment: a join,
`parent`, `with_name()` and the children a listing yields all name another
path on the same URL, and a token carried in the query follows them."""

from __future__ import annotations

import pytest

from pathapi import FileStat
from uripath import URI, URIPath

BASE = "unk://h/d/f.txt?sig=abc#frag"
KEPT = "?sig=abc#frag"

DERIVATIONS = {
    "join": (lambda p: p / "g", "unk://h/d/f.txt/g"),
    "join-nested": (lambda p: p / "g/h", "unk://h/d/f.txt/g/h"),
    "join-dotted": (lambda p: p / "../g", "unk://h/d/g"),
    "join-absolute": (lambda p: p / "/g", "unk://h/g"),
    "join-empty-segments": (lambda p: p / "g//", "unk://h/d/f.txt/g//"),
    "join-empty-key": (lambda p: p / "", "unk://h/d/f.txt"),
    "joinpath": (lambda p: p.joinpath("g", "h"), "unk://h/d/f.txt/g/h"),
    "parent": (lambda p: p.parent, "unk://h/d"),
    "parents": (lambda p: p.parents[1], "unk://h/"),
    "with_name": (lambda p: p.with_name("z.bin"), "unk://h/d/z.bin"),
    "with_stem": (lambda p: p.with_stem("z"), "unk://h/d/z.txt"),
    "with_suffix": (lambda p: p.with_suffix(".py"), "unk://h/d/f.py"),
    "with_segments": (lambda p: p.with_segments("", "x", "y"), "unk://h/x/y"),
    "with_path": (lambda p: p.with_path("/x"), "unk://h/x"),
    "relative_to": (lambda p: p.relative_to("unk://h/d"), "f.txt"),
}


@pytest.mark.parametrize("cls", [URI, URIPath])
@pytest.mark.parametrize("name", DERIVATIONS)
def test_a_path_only_derivation_keeps_the_query_and_the_fragment(cls, name):
    derive, path = DERIVATIONS[name]
    derived = derive(cls(BASE))
    assert derived.as_uri() == path + KEPT
    assert str(derived.query) == "sig=abc"
    assert derived.fragment == "frag"


@pytest.mark.parametrize("cls", [URI, URIPath])
def test_a_child_joined_back_onto_its_parent_is_the_same_uri(cls):
    child = cls(BASE)
    assert child.parent / child.name == child


@pytest.mark.parametrize("cls", [URI, URIPath])
def test_a_join_without_a_query_or_fragment_adds_none(cls):
    assert (cls("unk://h/d") / "f").as_uri() == "unk://h/d/f"


@pytest.mark.parametrize("cls", [URI, URIPath])
def test_a_uri_argument_of_a_join_keeps_its_own_query(cls):
    # A `URI` argument is joined as the constructor joins it: the last
    # segment that sets a query decides.
    base = cls(BASE)
    assert str((base / URI("g?x=1")).query) == "x=1"
    assert str((base / URI("g")).query) == "sig=abc"


class QueryListingPath(URIPath):
    """A scheme whose directory `root` lists a file and a directory."""

    __SCHEMES = ("qlistg5",)
    __slots__ = ()

    _TREE = {
        "root": [("a.txt", False), ("sub", True)],
        "sub": [("b.txt", False)],
    }

    def stat(self, *, follow_symlinks=True):
        return FileStat(is_dir=self.name in self._TREE)

    def _scandir(self):
        for name, is_dir in self._TREE[self.name]:
            yield name, FileStat(is_dir=is_dir, size_known=False)


def test_the_children_of_a_listing_keep_the_query_and_the_fragment_of_the_directory():
    root = URIPath("qlistg5://h/root?token=t#top")
    assert isinstance(root, QueryListingPath)
    listed = sorted(child.as_uri() for child in root.iterdir())
    assert listed == [
        "qlistg5://h/root/a.txt?token=t#top",
        "qlistg5://h/root/sub?token=t#top",
    ]


def test_glob_and_walk_yield_children_that_keep_the_query_and_the_fragment():
    root = URIPath("qlistg5://h/root?token=t#top")
    assert sorted(child.as_uri() for child in root.glob("*")) == [
        "qlistg5://h/root/a.txt?token=t#top",
        "qlistg5://h/root/sub?token=t#top",
    ]
    assert sorted(child.as_uri() for child in root.rglob("*.txt")) == [
        "qlistg5://h/root/a.txt?token=t#top",
        "qlistg5://h/root/sub/b.txt?token=t#top",
    ]
    assert sorted(directory.as_uri() for directory, _, _ in root.walk()) == [
        "qlistg5://h/root/sub?token=t#top",
        "qlistg5://h/root?token=t#top",
    ]


def test_a_str_destination_takes_neither_the_query_nor_the_fragment_of_its_source():
    # A signature in the query signs the source only: a sibling named by a
    # string is another resource.
    source = URIPath("unk://h/d/f.txt?sig=S#frag")
    assert source._coerce_target("g.txt").as_uri() == "unk://h/d/g.txt"
    assert source._rename_target("g.txt").as_uri() == "unk://h/d/g.txt"
    assert source._rename_target("../g.txt").as_uri() == "unk://h/g.txt"
