"""`pathlib_next.protocols.supports()` on URI classes: what a class claims is
what it can do, for `data:` and for a scheme that delegates to a core path."""

from __future__ import annotations

import pytest

from pathlib_next import MemPath
from pathlib_next.mempath import MemPathBackend
from pathlib_next.protocols import (
    BinaryOpen,
    Chmod,
    Create,
    Listing,
    Remove,
    Stat,
    Utime,
    capabilities,
    supports,
)

from uripath import URIPath
from uripath.schemes import DelegatingURIPath

STORE = MemPathBackend()


class ListingURIPath(DelegatingURIPath):
    __SCHEMES = ("capslisting",)
    __slots__ = ()
    _DELEGATED = ("_scandir", "_open", "_mkdir", "unlink", "rmdir", "_utime")

    def _make_core(self):
        return MemPath(self.path or "/", backend=STORE)


class NoTimesURIPath(DelegatingURIPath):
    """Names `_utime` but its core path cannot set a time."""

    __SCHEMES = ("capsnotimes",)
    __slots__ = ()
    _DELEGATED = ("_scandir", "_open", "_utime")

    def _make_core(self):
        class NoTimes(MemPath):
            __slots__ = ()
            _utime = Utime._utime

        return NoTimes(self.path or "/", backend=STORE)


def test_a_data_uri_does_not_claim_listing():
    data = URIPath.scheme_class("data")
    assert Listing not in capabilities(data)
    assert {Stat, BinaryOpen} <= capabilities(data)
    assert not supports(data, Create) and not supports(data, Remove)


def test_a_data_uri_still_raises_not_a_directory_when_listed():
    with pytest.raises(NotADirectoryError):
        list(URIPath("data:text/plain,a").iterdir())


def test_a_scheme_that_lists_through_scandir_or_listdir_claims_listing():
    assert supports(ListingURIPath, Listing)
    assert supports(URIPath.scheme_class("ftp"), Listing)
    assert supports(URIPath.scheme_class("file"), Listing)


def test_a_uri_class_that_defines_no_listing_primitive_does_not_claim_it():
    class NoListing(URIPath):
        __SCHEMES = ("capsnolisting",)
        __slots__ = ()

    assert not supports(NoListing, Listing)


def test_an_instance_of_a_delegating_scheme_answers_with_its_core_path():
    path = URIPath("capslisting://h/x")
    assert supports(path, Listing, Create, Remove, Utime)
    assert capabilities(path) >= {Listing, Create, Remove, Utime}


def test_a_delegated_hook_the_core_path_lacks_reads_as_absent():
    path = URIPath("capsnotimes://h/x")
    assert supports(type(path), Utime)
    assert not supports(path, Utime)
    assert supports(path, Listing)


def test_a_protocol_the_class_has_no_hook_for_stays_absent_whatever_the_core_says():
    path = URIPath("capslisting://h/x")
    assert not supports(path, Chmod)
