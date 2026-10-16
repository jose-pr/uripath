import os
import pathlib

import pytest

import pathapi
from uripath import URI

test_uris = ["http://user:pass@google.com:80"]


def parse_uri(_uri: str):
    uri = URI(_uri)
    assert uri.as_uri() == _uri
    return uri


def test_source():
    uri = parse_uri(test_uris[0])
    assert uri.source.scheme == "http"
    assert uri.source.host == "google.com"
    assert uri.source.port == 80
    assert uri.source.parsed_userinfo() == ("user", "pass")


def test_no_scheme():
    uri = parse_uri("//user:pass@google.com:80/")
    assert uri.source.scheme == None
    assert uri.source.host == "google.com"
    assert uri.source.port == 80
    assert uri.source.parsed_userinfo() == ("user", "pass")


def test_no_scheme_with_host_no_pass():
    uri = parse_uri("//user@google.com:80/")
    assert uri.source.scheme == None
    assert uri.source.host == "google.com"
    assert uri.source.port == 80
    assert uri.source.parsed_userinfo() == ("user", "")


def test_no_scheme_no_host():
    uri = parse_uri("//user@:80/")
    assert uri.source.scheme == None
    assert uri.source.host == ""
    assert uri.source.port == 80
    assert uri.source.parsed_userinfo() == ("user", "")


def test_no_scheme_no_netloc():
    uri = parse_uri("//user@")
    assert uri.source.scheme == None
    assert uri.source.host == ""
    assert uri.source.port == None
    assert uri.source.parsed_userinfo() == ("user", "")


def test_path():
    uri = parse_uri("http://google.com/root/subroot/filename.ext")
    assert uri.source.scheme == "http"
    assert uri.source.host == "google.com"
    assert uri.source.port == None
    assert uri.source.parsed_userinfo() == ("", "")
    assert uri.path == "/root/subroot/filename.ext"


def test_encoded_path():
    uri = URI(
        "http://goog%2Fe.com/root/subroot/%3Fquery/%23fragment/%2Fencoded%2Ffilename.ext"
    )
    assert uri.source.scheme == "http"
    assert uri.source.host == "goog/e.com"
    assert uri.source.port == None
    assert uri.source.parsed_userinfo() == ("", "")
    assert uri.path == "/root/subroot/?query/#fragment//encoded/filename.ext"


def test_child():
    sftp_root = URI("sftp://root@sftpexample/")
    authkeys = sftp_root / "root/.ssh/authorized_keys"
    uri = authkeys.as_uri()
    assert uri == "sftp://root@sftpexample/root/.ssh/authorized_keys"


def test_truediv_pathlib():
    sftp_root = URI("sftp://root@sftpexample/")
    authkeys = sftp_root / pathlib.PurePosixPath("root/.ssh/authorized_keys")
    uri = authkeys.as_uri()
    assert uri == "sftp://root@sftpexample/root/.ssh/authorized_keys"

    # A relative concrete Path joins like a relative PurePath and keeps the
    # base's source, and is not the LOCAL file
    # "file:/root/.ssh/authorized_keys".
    authkeys = sftp_root / pathlib.Path("root/.ssh/authorized_keys")
    uri = authkeys.as_uri()
    assert uri == "sftp://root@sftpexample/root/.ssh/authorized_keys"

    # An absolute one still replaces the base, as a local file: URI.
    absolute = pathlib.Path("/root/.ssh/authorized_keys").absolute()
    assert (sftp_root / absolute).as_uri() == URI(absolute.as_uri()).as_uri()


def test_join_without_root():
    authkeys = URI("sftp://root@sftpexample") / "root/.ssh/authorized_keys"
    uri = authkeys.as_uri()
    assert uri == "sftp://root@sftpexample/root/.ssh/authorized_keys"


def test_fspath_raises_for_non_host_filesystem_scheme():
    # URI (pure, no _host_filesystem_path override) must keep raising for a
    # remote scheme whose .path has no meaning as a filesystem path -- e.g.
    # http: is a URL path component, not a path on the host's filesystem.
    uri = URI("http://user:pass@example.com/a/b")
    with pytest.raises(NotImplementedError):
        os.fspath(uri)
    with pytest.raises(NotImplementedError):
        uri.host_fspath()


def test_str_sanitizes_password_but_as_uri_full_round_trips():
    uri = URI("http://user:pass@example.com/a/b")
    assert str(uri) == "http://user@example.com/a/b"
    assert uri.as_uri(sanitize=False) == "http://user:pass@example.com/a/b"


def test_source_str_and_repr_redact_password():
    # repr() is what a traceback frame renders, so a Source anywhere on a
    # failing call stack would leak the credential if it showed the userinfo
    # as it is. Both redact the same way URI.__str__() does.
    from uripath.source import Source

    source = Source("ftp", "root:secret", "nas", 22)
    assert "secret" not in str(source)
    assert "secret" not in repr(source)
    assert str(source) == "ftp://root@nas:22"
    assert repr(source) == "Source(scheme='ftp', userinfo='root', host='nas', port=22)"


def test_source_str_is_not_a_connectable_uri():
    # str(source) carries no password, so it does not rebuild a working
    # authority: every real connection site reads individual Source fields
    # (.host/.port/.userinfo/parsed_userinfo()), never the whole object. The
    # round trip, for a caller that needs it, is reveal() (mirrors
    # URI.as_uri(sanitize=False)).
    from uripath.source import Source

    source = Source("sftp", "root:secret", "nas", 22)
    assert str(source) != "sftp://root:secret@nas:22"
    assert source.reveal() == "sftp://root:secret@nas:22"


def test_source_str_is_the_sanitized_text():
    from uripath.source import Source

    source = Source("ftp", "root:secret", "nas", 22)
    assert str(source) == "ftp://root@nas:22"


def test_source_userinfo_field_still_carries_password():
    # Redaction is display-only (__str__/__repr__) -- the actual data
    # access API (.userinfo, parsed_userinfo(), keys()/__getitem__) must
    # still return the real password; only rendering is sanitized.
    from uripath.source import Source

    source = Source("sftp", "root:secret", "nas", 22)
    assert source.userinfo == "root:secret"
    assert source.parsed_userinfo() == ("root", "secret")
    assert source["userinfo"] == "root:secret"


# --- URI.__init__ from various source types ---


def test_from_pure_posix_path():
    # PurePosixPath isn't a pathlib.Path (no as_uri()), so this exercises
    # the plain-Pathname/PurePath branch of URI.__init__.
    uri = URI(pathlib.PurePosixPath("a/b/c"))
    assert uri.path.endswith("a/b/c")


def test_from_fspath_only_object():
    # An object that only implements __fspath__ (no as_posix()) is read
    # through os.fspath().
    class FspathOnly:
        def __fspath__(self):
            return "a/b/c.txt"

    uri = URI(FspathOnly())
    assert uri.path.endswith("a/b/c.txt")


def test_from_relative_local_path_no_crash():
    # pathlib.Path.as_uri() raises ValueError for relative paths; URI()
    # must fall back cleanly instead of propagating a bare except.
    uri = URI(pathlib.Path("relative/path.txt"))
    assert "relative/path.txt" in uri.path


# --- query/fragment: "last segment that sets one wins" ---


def test_join_query_fragment_last_setting_segment_wins():
    # A later segment with NO query/fragment must not blank out an earlier
    # segment's -- only a later segment that actually sets one should win.
    base = URI("http://h/a?x=1#frag")
    joined = URI(base, "b")
    assert str(joined.query) == "x=1"
    assert joined.fragment == "frag"


def test_join_query_fragment_later_segment_overrides():
    base = URI("http://h/a?x=1")
    joined = URI(base, "b?y=2#frag2")
    assert str(joined.query) == "y=2"
    assert joined.fragment == "frag2"
