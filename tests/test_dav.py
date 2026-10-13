"""DAVURIPath-specific regression coverage (generic contract behavior lives in
test_contract.py::TestDavContract).
"""

import pytest

from uripath import URIPath
from uripath.schemes import DAVURIPath

pytestmark = pytest.mark.usefixtures("http_transport_kind")


def test_dav_scheme_resolves_via_entry_point(dav_server):
    # Regression for a stale editable-install `entry_points.txt` (found
    # while verifying this fix): after the webdav.py -> dav.py rename
    # (6cd1ba8), `URIPath("dav://...")` raised ModuleNotFoundError for
    # `uripath.schemes.webdav` because the installed package
    # metadata wasn't regenerated. TestDavContract's `root()` fixture
    # constructs `DAVURIPath(...)` directly and so never exercised the
    # entry-point lookup path that real callers use.
    p = URIPath(f"{dav_server}/a.txt")
    assert isinstance(p, DAVURIPath)


def test_dav_rmdir_on_file_raises_notadirectoryerror(dav_server):
    # Same bug class as HTTPURIPath.rmdir(): a PROPFIND
    # Depth:1 on a non-collection resource returns only the "." entry
    # describing itself, which _scandir() filters out -- so a *file*
    # looked exactly like an empty directory and rmdir() silently
    # DELETEd it.
    p = DAVURIPath(f"{dav_server}/a.txt")
    assert p.exists()
    with pytest.raises(NotADirectoryError):
        p.rmdir()
    assert p.exists()


def test_dav_rmdir_empty_dir(dav_server):
    p = DAVURIPath(f"{dav_server}/empty_dir")
    p.rmdir()
    assert not p.exists()


def test_dav_rmdir_not_empty_raises_enotempty(dav_server):
    import errno

    p = DAVURIPath(f"{dav_server}/sub")
    with pytest.raises(OSError) as excinfo:
        p.rmdir()
    assert excinfo.value.errno == errno.ENOTEMPTY
    assert p.exists()
