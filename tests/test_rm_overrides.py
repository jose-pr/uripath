"""Every scheme that overrides `rm()` keeps the signature of `Path.rm()`.

The override takes its own route for a recursive removal (one DAV DELETE).
`follow_symlinks=` and `follow_binds=` are keywords of `Path.rm()`, so the
override accepts them, checks them before anything is sent, and forwards them
wherever the generic removal runs. The signatures and the argument checks are
read without a call to a server.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("uritools")

from pathlib_next import Path
from uripath.schemes import dav

CASES = [(dav.DAVURIPath, "dav://host/dir")]
IDS = [cls.__name__ for cls, _ in CASES]


@pytest.mark.parametrize("cls, url", CASES, ids=IDS)
def test_rm_override_has_the_signature_of_path_rm(cls, url):
    expected = inspect.signature(Path.rm).parameters
    actual = inspect.signature(cls.rm).parameters
    assert list(actual) == list(expected)
    for name, parameter in expected.items():
        assert actual[name].kind == parameter.kind, name
        assert actual[name].default == parameter.default, name


@pytest.mark.parametrize("cls, url", CASES, ids=IDS)
def test_rm_non_recursive_forwards_the_policies(monkeypatch, cls, url):
    seen = {}

    def record(self, *args, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(Path, "rm", record)
    policy = lambda path: None
    cls(url).rm(follow_symlinks=policy, follow_binds=None)
    assert seen["follow_symlinks"] is policy
    assert seen["follow_binds"] is None


@pytest.mark.parametrize("keyword", ["follow_symlinks", "follow_binds"])
@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("cls, url", CASES, ids=IDS)
def test_rm_checks_the_policies_before_anything_is_sent(cls, url, recursive, keyword):
    """No client exists in these paths, so a request would not fail with
    `ValueError`."""
    with pytest.raises(ValueError, match="True, False, None or a callable"):
        cls(url).rm(recursive=recursive, ignore_error=True, **{keyword: "always"})
