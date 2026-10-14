"""Filesystem contract shared by every Path implementation.

This is the reusable "one test class, many backends" pattern the project
wants third-party implementers (custom Path subclasses like MemPath, or
URIPath schemes) to be able to run against their own implementation -- see
`docs/guides/extending.md`.
"""

import os
import pickle
import stat

import pytest

from capabilities import stores_question_marks

import pathlib_next
from pathlib_next.mempath import MemPath
from pathlib_next.testing import (
    PathContract,
    PurePathContract,
    ReadPathContract,
    populate_fixture_tree,
)
from uripath.schemes import FileURIPath
from uripath.schemes import DataURIPath
from uripath import URIPath
from uripath.schemes import ZipURIPath, TarURIPath


def make_zip_from_local(local_dir, zip_path):
    import zipfile

    with zipfile.ZipFile(zip_path, "w") as zf:
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, local_dir).replace("\\", "/")
                zf.write(full_path, rel_path)
            for d in dirs:
                full_path = os.path.join(root, d)
                if not os.listdir(full_path):
                    rel_path = (
                        os.path.relpath(full_path, local_dir).replace("\\", "/") + "/"
                    )
                    zf.writestr(rel_path, "")


def make_tar_from_local(local_dir, tar_path):
    import tarfile

    with tarfile.open(tar_path, "w") as tf:
        for root, dirs, files in os.walk(local_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, local_dir).replace("\\", "/")
                tf.add(full_path, arcname=rel_path)
            for d in dirs:
                full_path = os.path.join(root, d)
                if not os.listdir(full_path):
                    rel_path = os.path.relpath(full_path, local_dir).replace("\\", "/")
                    tf.add(full_path, arcname=rel_path)


# Writable, full RW contract backends
class TestLocalContract(PathContract):
    supports_question_mark_names = stores_question_marks()

    @pytest.fixture
    def root(self, fixture_tree):
        return pathlib_next.LocalPath(fixture_tree)


class TestMemContract(PathContract):
    # MemPath has no rename(); move() falls back to copy + delete.
    supports_rename = False
    supports_question_mark_names = True

    @pytest.fixture
    def root(self):
        return populate_fixture_tree(MemPath("/"))


class TestFileURIPathContract(PathContract):
    supports_question_mark_names = stores_question_marks()

    @pytest.fixture
    def root(self, fixture_tree):
        return FileURIPath(fixture_tree.as_uri())


# HTTP read-only contract
class TestHttpContract(ReadPathContract):
    # One URL serves an index page or a file: listing a file and reading a
    # directory cannot be told apart from the response.
    distinguishes_file_types = False

    @pytest.fixture
    def root(self, http_server, http_transport_kind):
        from uripath.schemes import HTTPURIPath

        return HTTPURIPath(http_server)


# Zip read/write contract (local outer archive -- full mutation support:
# unlink/rmdir/rename/overwrite, see polish_perf/09)
class TestZipContract(PathContract):
    # Members are rewritten whole; open("a") raises NotImplementedError.
    supports_append = False
    supports_question_mark_names = True
    # A zip member's time is the one written with the member: no `_utime()`.
    supports_utime = False

    @pytest.fixture
    def root(self, tmp_path_factory, fixture_tree):
        # Outside fixture_tree (which is tmp_path): an archive built inside
        # the tree it archives lists itself.
        zip_file = tmp_path_factory.mktemp("zip") / "tree.zip"
        make_zip_from_local(fixture_tree, zip_file)
        return ZipURIPath(f"zip:{zip_file.as_uri()}!/")


# Tar read-only contract
class TestTarContract(ReadPathContract):
    @pytest.fixture
    def root(self, tmp_path_factory, fixture_tree):
        tar_file = tmp_path_factory.mktemp("tar") / "tree.tar"
        make_tar_from_local(fixture_tree, tar_file)
        return TarURIPath(f"tar:{tar_file.as_uri()}!/")


# `archive:` picks the format from the outer file's extension; `archive+zip:`
# and `archive+tar:` pin it. Same trees as the `zip:` and `tar:` classes.
class TestArchiveZipContract(PathContract):
    supports_append = False
    supports_question_mark_names = True
    supports_utime = False

    scheme = "archive"

    @pytest.fixture
    def root(self, tmp_path_factory, fixture_tree):
        zip_file = tmp_path_factory.mktemp("archive-zip") / "tree.zip"
        make_zip_from_local(fixture_tree, zip_file)
        return URIPath(f"{self.scheme}:{zip_file.as_uri()}!/")


class TestArchivePinnedZipContract(TestArchiveZipContract):
    scheme = "archive+zip"


class TestArchiveTarContract(ReadPathContract):
    scheme = "archive"

    @pytest.fixture
    def root(self, tmp_path_factory, fixture_tree):
        tar_file = tmp_path_factory.mktemp("archive-tar") / "tree.tar"
        make_tar_from_local(fixture_tree, tar_file)
        return URIPath(f"{self.scheme}:{tar_file.as_uri()}!/")


class TestArchivePinnedTarContract(TestArchiveTarContract):
    scheme = "archive+tar"


# DataURIPath read-only contract (represents single file)
class TestDataURIPathContract(ReadPathContract):
    supports_listing = False

    @pytest.fixture
    def root(self):
        return DataURIPath("data:text/plain,a")

    def _single_resource(self):
        pytest.skip("a data: URI is a single resource with no children")

    def test_exists_and_types(self, root):
        assert root.exists()
        assert root.is_file()
        assert not root.is_dir()

    def test_read_text_and_bytes(self, root):
        assert root.read_text() == "a"
        assert root.read_bytes() == b"a"

    def test_iterdir_lists_children(self, root):
        with pytest.raises(NotADirectoryError):
            list(root.iterdir())

    def test_stat(self, root):
        st = root.stat()
        assert st.st_size == 1

    def test_open_read_modes(self, root):
        with root.open() as fh:
            assert fh.read() == "a"
        with root.open("rt") as fh:
            assert fh.read() == "a"
        with root.open("rb") as fh:
            assert fh.read() == b"a"

    def test_stat_tells_a_directory_from_a_file(self, root):
        assert stat.S_ISREG(root.stat().st_mode)
        assert not stat.S_ISDIR(root.stat().st_mode)

    def test_stat_missing_raises_file_not_found(self, root):
        self._single_resource()

    def test_read_missing_raises_file_not_found(self, root):
        self._single_resource()

    def test_read_directory_raises(self, root):
        self._single_resource()

    def test_nothing_exists_below_a_file(self, root):
        self._single_resource()

    def test_partial_reads_continue_where_the_last_stopped(self, root):
        self._single_resource()

    # A data: URI has no names, parents or children: the pure-path surface
    # raises, and the contract's hierarchical examples read that instead.
    def test_pure_basics(self, root):
        for name in ("name", "suffix", "stem", "parent", "parents"):
            with pytest.raises(NotImplementedError):
                getattr(root, name)

    def test_pure_joinpath_truediv(self, root):
        with pytest.raises(NotImplementedError):
            root / "b"
        with pytest.raises(NotImplementedError):
            root.joinpath("b", "c")

    def test_pure_match(self, root):
        with pytest.raises(NotImplementedError):
            root.match("*.txt")

    def test_a_pickled_path_is_equal_to_the_original(self, root):
        again = pickle.loads(pickle.dumps(root))
        assert type(again) is type(root)
        assert again == root
        assert hash(again) == hash(root)


# Ftp contract
class TestFtpContract(PathContract):
    # The loopback server keeps the names on this machine's file system.
    supports_question_mark_names = stores_question_marks()

    @pytest.fixture
    def root(self, ftp_server):
        from uripath.schemes import FTPURIPath

        return FTPURIPath(ftp_server)


# WebDAV contract
class TestDavContract(PathContract):
    # Uploads are whole-resource PUTs; open("a") raises NotImplementedError.
    supports_append = False
    # The test server (WsgiDAV) cuts a MOVE destination at a percent-decoded
    # "?", so a rename to such a name lands under the part before it.
    supports_question_mark_names = False
    # WebDAV keeps a resource's time as the server's own property.
    supports_utime = False

    @pytest.fixture
    def root(self, dav_server, http_transport_kind):
        from uripath.schemes import DAVURIPath

        return DAVURIPath(dav_server)
