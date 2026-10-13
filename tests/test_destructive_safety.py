"""Generic copy/move/rm must never destroy data they were not asked to.

Each test asserts what has to SURVIVE (the destination, the source, files
outside the tree) -- "an exception was raised" alone passed against the
defects these guard: a failed copy emptied its target, a same-file copy or
case-only move deleted the file, move(overwrite=True) removed the target
before discovering the source was missing, and rm(recursive=True) walked
through Windows junctions and file: directory symlinks.
"""

import os
import pathlib
import subprocess

import pytest
from capabilities import can_make_junctions, requires_junctions, requires_uri_extra

import pathlib_next
from pathlib_next.mempath import MemPath
from pathlib_next.sync import PathSyncer

LocalPath = pathlib_next.LocalPath


# --- copy -----------------------------------------------------------------








@requires_uri_extra
def test_copy_http_404_source_leaves_local_target_intact(http_server, tmp_path):
    from uripath import UriPath

    target = LocalPath(tmp_path / "cache.json")
    target.write_text("GOOD CACHE")
    with pytest.raises(FileNotFoundError):
        UriPath(http_server + "/no-such-file.json").copy(target, overwrite=True)
    assert target.read_text() == "GOOD CACHE"










# --- move -----------------------------------------------------------------














# --- move and copy: one file under several names -------------------------


@pytest.fixture(params=["local", "mem"])
def disk(request, tmp_path):
    """An empty directory on the local disk, and one in memory."""
    return LocalPath(tmp_path) if request.param == "local" else MemPath("/")


def _nested(root):
    """`root/dst`, holding `other.txt` and `sub/data.txt`."""
    dst = root / "dst"
    (dst / "sub").mkdir(parents=True)
    (dst / "other.txt").write_text("OTHER")
    (dst / "sub" / "data.txt").write_text("DATA")
    return dst


def _both_trees_survive(dst):
    assert (dst / "other.txt").read_text() == "OTHER"
    assert (dst / "sub" / "data.txt").read_text() == "DATA"


def _tolerate_refusal(operation):
    """Whether the operation refused (`OSError`) or did nothing is not what
    these tests are about; what survives is."""
    try:
        operation()
    except OSError:
        pass


def _symlink_or_skip(link, target, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink unavailable: {error}")
















def _as_another_class(kind, path):
    """The file `path` names, as an instance of another class."""
    if kind == "subclass":

        class SubLocal(LocalPath):
            __slots__ = ()

        return SubLocal(path)
    if kind == "stdlib":
        return pathlib.Path(path)
    pytest.importorskip("uritools")
    from uripath import UriPath

    return UriPath(path)


@pytest.mark.parametrize("kind", ["subclass", "stdlib", "file-uri"])
def test_move_onto_the_same_file_under_another_class_keeps_it(tmp_path, kind):
    path = LocalPath(tmp_path / "f.txt")
    path.write_text("PRECIOUS")
    _tolerate_refusal(lambda: path.move(_as_another_class(kind, path), overwrite=True))
    assert path.read_text() == "PRECIOUS"


@pytest.mark.parametrize("kind", ["subclass", "file-uri"])
def test_move_directory_onto_the_same_directory_under_another_class_keeps_it(
    tmp_path, kind
):
    dst = _nested(LocalPath(tmp_path))
    _tolerate_refusal(lambda: dst.move(_as_another_class(kind, dst), overwrite=True))
    _both_trees_survive(dst)


@pytest.mark.parametrize("kind", ["subclass", "file-uri"])
def test_copy_onto_the_same_file_under_another_class_raises_and_keeps_it(
    tmp_path, kind
):
    path = LocalPath(tmp_path / "f.txt")
    path.write_text("PRECIOUS")
    with pytest.raises(OSError, match="same file"):
        path.copy(_as_another_class(kind, path), overwrite=True)
    assert path.read_text() == "PRECIOUS"


def _hard_link_or_skip(existing, new):
    try:
        os.link(existing, new)
    except (OSError, NotImplementedError, AttributeError) as error:
        pytest.skip(f"hard link unavailable: {error}")




















# --- rm through links -----------------------------------------------------


def _junction_or_skip(link, target):
    if not can_make_junctions():
        pytest.skip("this system cannot create directory junctions")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not os.path.lexists(link):
        pytest.skip(f"could not create junction: {result.stderr.strip()}")


def _victim(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("V")
    return victim






def test_file_uri_rm_recursive_does_not_descend_into_junction(tmp_path):
    pytest.importorskip("uritools")
    from uripath import UriPath

    victim = _victim(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    _junction_or_skip(tree / "j", victim)
    UriPath(LocalPath(tree)).rm(recursive=True)
    assert not tree.exists()
    assert (victim / "keep.txt").read_text() == "V"


def test_file_uri_rm_recursive_does_not_follow_directory_symlink(tmp_path):
    pytest.importorskip("uritools")
    from uripath import UriPath

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("P")
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_text("a")
    try:
        os.symlink(outside, tree / "link", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    UriPath(LocalPath(tree)).rm(recursive=True)

    assert (outside / "precious.txt").read_text() == "P"
    assert not os.path.lexists(tree / "link")


def test_file_uri_scandir_reports_symlink_not_directory(tmp_path):
    pytest.importorskip("uritools")
    from uripath import UriPath

    (tmp_path / "real").mkdir()
    try:
        os.symlink(tmp_path / "real", tmp_path / "link", target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory symlink unavailable: {error}")

    stats = dict(UriPath(LocalPath(tmp_path))._scandir())
    assert stats["link"].is_symlink()
    assert not stats["link"].is_dir()
    assert stats["real"].is_dir()


# --- untrusted child names ------------------------------------------------










# --- a binding is not a symlink -------------------------------------------








# --- rm(follow_symlinks=, follow_binds=) ----------------------------------


@pytest.fixture
def tree_with_link_and_binding(tmp_path):
    """A tree holding one symlink, and on Windows one binding too, both
    pointing at a directory OUTSIDE the tree, plus a file of its own."""
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "keep.txt").write_text("PRECIOUS")
    (tmp_path / "tree").mkdir()
    (tmp_path / "tree" / "own.txt").write_text("mine")
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(
            str(tmp_path / "target"), str(tmp_path / "tree" / "bind")
        )
    # A bind mount needs privileges, so the binding half is Windows-only;
    # `is_mount()` covers the POSIX side elsewhere.
    _symlink_or_skip(tmp_path / "tree" / "link", tmp_path / "target", directory=True)
    return tmp_path


#: What `tree_with_link_and_binding` puts besides `own.txt` in `tree`.
LINK_NAMES = ["bind", "link"] if os.name == "nt" else ["link"]


def _tolerate(errors):
    def handler(error, path):
        errors.append((type(error).__name__, path.name))
        return True

    return handler


















def _tree_with_one_link(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("P")
    link = tmp_path / "link"
    _symlink_or_skip(link, outside, directory=True)
    return LocalPath(link), outside








# --- names only Windows rewrites ------------------------------------------


@pytest.fixture
def windows_flavoured(monkeypatch):
    """Every path counts as one read with Windows rules, so the rule runs on
    any platform against `MemPath`."""
    from pathlib_next import _names

    monkeypatch.setattr(_names, "is_windows_flavoured", lambda path: True)


def _refused(errors):
    return sorted(str(error) for error in errors if isinstance(error, ValueError))


def test_copy_recursive_never_merges_names_windows_rewrites(windows_flavoured):
    source = MemPath("/rewrite-src")
    source.mkdir()
    for name in ("report", "report.", "a ", "nul", "Con.txt", "ok.txt"):
        (source / name).write_text(f"data:{name}")
    target = MemPath("/rewrite-dst")
    errors = []

    source.copy(target, recursive=True, ignore_error=errors.append)

    assert sorted(child.name for child in target.iterdir()) == ["ok.txt", "report"]
    assert (target / "report").read_text() == "data:report"
    refused = _refused(errors)
    assert len(refused) == 4
    for name in ("report.", "a ", "nul", "Con.txt"):
        assert any(repr(name) in message for message in refused), name


def test_sync_never_merges_names_windows_rewrites(windows_flavoured):
    source = MemPath("/rewrite-sync-src")
    source.mkdir()
    for name in ("report", "report.", "nul", "ok.txt"):
        (source / name).write_text(f"data:{name}")
    target = MemPath("/rewrite-sync-dst")
    errors = []

    PathSyncer(
        lambda entry: entry.stat.st_size,
        ignore_error=lambda error, *args: errors.append(error) or True,
    ).sync(source, target)

    assert sorted(child.name for child in target.iterdir()) == ["ok.txt", "report"]
    assert (target / "report").read_text() == "data:report"
    assert len(_refused(errors)) == 2




