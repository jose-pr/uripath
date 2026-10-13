"""URI core soundness and core copy/open parity (wave 5, group G5).

Each test asserts an outcome -- the bytes a server received, the decoded
pairs, the class and URI a join produced, what exists on disk -- not merely
that nothing raised.
"""

from __future__ import annotations

import errno
import http.server
import os
import pathlib
import socket
import stat
import threading
import unittest.mock as mock

import pytest

import pathlib_next
from pathlib_next.mempath import MemPath
from uripath import URI, URIPath
from uripath.query import Query
from uripath.schemes.file import FileURIPath

# --- query: kept encoded, sent unchanged, decoded once (Design Q1) ---------


@pytest.fixture
def recording_http_server():
    """A loopback HTTP server that records each request line's target."""
    seen: list[str] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_HEAD = do_GET

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_http_request_carries_the_encoded_query_unchanged(recording_http_server):
    base, seen = recording_http_server
    URIPath(f"{base}/download?name=a%26b&sig=ab%2Bcd%3D%3D").read_bytes()
    # It used to go out as "name=a&b&sig=ab+cd==": a presigned signature
    # broken and an extra parameter injected.
    assert "/download?name=a%26b&sig=ab%2Bcd%3D%3D" in seen


def test_http_request_with_dict_query_is_encoded_once(recording_http_server):
    base, seen = recording_http_server
    URIPath(f"{base}/search").with_query({"q": "a b", "k": "x&y"}).read_bytes()
    assert "/search?q=a%20b&k=x%26y" in seen


def test_parsed_query_is_the_received_encoded_string():
    uri = URI("http://h/download?name=a%26b&sig=ab%2Bcd%3D%3D")
    assert uri.query == "name=a%26b&sig=ab%2Bcd%3D%3D"
    assert uri.as_uri() == "http://h/download?name=a%26b&sig=ab%2Bcd%3D%3D"


def test_query_to_dict_decodes_each_value_exactly_once():
    query = Query(URI("http://h/?q=a%26b&x=1%3D2&t=abc%2Bdef%3D&v=%2541").query)
    assert query.to_dict() == {
        "q": ["a&b"],
        "x": ["1=2"],
        "t": ["abc+def="],
        "v": ["%41"],
    }


def test_query_key_containing_equals_round_trips():
    assert Query({"a=b": "c"}).decode() == [("a=b", "c")]
    assert Query([("k=", "v")]).to_dict() == {"k=": ["v"]}


def test_query_characters_illegal_on_the_wire_are_encoded():
    assert URI("http://h/?q=a b").as_uri() == "http://h/?q=a%20b"
    assert URI("http://h/?p=100%").as_uri() == "http://h/?p=100%25"


# --- remote / relative concrete Path keeps the remote (Design Q2) ----------


@pytest.mark.parametrize(
    "relative",
    [pathlib.Path("etc/x"), pathlib_next.LocalPath("etc/x")],
    ids=["pathlib.Path", "LocalPath"],
)
def test_remote_join_with_relative_concrete_path_stays_remote(relative):
    joined = URIPath("ftp://root@host/srv/") / relative
    assert type(joined).__name__ == "FTPURIPath"
    assert joined.as_uri() == "ftp://root@host/srv/etc/x"
    assert URIPath("ftp://root@host/srv/").joinpath(relative) == joined


def test_remote_join_with_absolute_concrete_path_is_a_local_file():
    local = pathlib.Path("etc/x").absolute()
    joined = URIPath("http://h/base/") / local
    assert isinstance(joined, FileURIPath)
    assert pathlib.Path(os.fspath(joined)) == local
    # joinpath dispatches the class from the scheme, as `/` does.
    assert isinstance(URIPath("http://h/base/").joinpath(local), FileURIPath)


def test_relative_concrete_path_alone_is_still_a_local_file():
    uri = URIPath(pathlib.Path("rel/x.txt"))
    assert isinstance(uri, FileURIPath)
    assert uri.path == "rel/x.txt"


# --- file: drive and UNC forms (Windows) -----------------------------------


@pytest.mark.skipif(os.name != "nt", reason="Windows drive letters")
def test_file_localhost_drive_uri_renders_and_hashes():
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    drive_path = pathlib.Path(windir).as_posix()
    uri = URIPath(f"file://localhost/{drive_path}")
    assert str(uri) == f"file://localhost/{drive_path}"
    assert repr(uri) == f"FileURIPath('file://localhost/{drive_path}')"
    assert uri in {uri}
    assert os.fspath(uri) == drive_path
    assert uri.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows drive letters")
def test_file_uri_of_local_path_matches_the_pure_uri(tmp_path):
    local = pathlib_next.LocalPath(tmp_path)
    assert URI(local) == URIPath(local)
    assert str(URIPath(local)) == str(URI(local))
    assert pathlib.Path(os.fspath(URIPath(local))) == tmp_path


@pytest.mark.skipif(os.name != "nt", reason="UNC paths")
def test_file_uri_naming_this_host_is_a_unc_share_not_a_local_folder():
    hostname = socket.gethostname()
    assert (
        os.fspath(URIPath(f"file://{hostname}/share/x.txt"))
        == f"//{hostname.lower()}/share/x.txt"
    )
    assert os.fspath(URIPath("file://127.0.0.1/c$/Windows")) == "//127.0.0.1/c$/Windows"


# --- scheme map: late registration and cached misses -----------------------


def test_scheme_class_defined_after_first_dispatch_is_found():
    URIPath("file:/a")  # the map is built and cached

    class LateG5Path(URIPath):
        __SCHEMES = ("late-g5",)

    assert type(URIPath("late-g5://h/a")) is LateG5Path


def test_unregistered_scheme_scans_entry_points_once():
    calls = []

    def entry_points(*args, **kwargs):
        calls.append(kwargs)
        return [] if kwargs.get("group") else {}

    with mock.patch("importlib.metadata.entry_points", side_effect=entry_points):
        for _ in range(3):
            assert type(URIPath("nosuch-g5:x")) is URIPath
    assert len(calls) == 1


# --- non-UTF-8 percent-escapes ----------------------------------------------


def test_non_utf8_escape_constructs_and_round_trips():
    uri = URI("http://h/caf%E9.html?x=%FF#fr%E9")
    assert uri.as_uri() == "http://h/caf%E9.html?x=%FF#fr%E9"
    assert uri.name.encode("utf-8", "surrogateescape") == b"caf\xe9.html"


def test_non_utf8_escape_constructs_a_scheme_path():
    path = URIPath("http://h/caf%E9.html")
    assert type(path).__name__ == "HTTPURIPath"
    assert str(path) == "http://h/caf%E9.html"


# --- copy(): symlinks, mode bits, own subtree --------------------------------


def _symlink_or_skip(link, target, target_is_directory=False):
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink unavailable: {error}")


# --- open(): mode validation like open() -------------------------------------


def test_data_uri_payload_is_opaque_and_decoded_once():
    assert URIPath("data:,a/./b").read_bytes() == b"a/./b"
    assert URIPath("data:text/plain,x/../y").read_bytes() == b"x/../y"
    assert URIPath("data:,100%2525").read_bytes() == b"100%25"
    binary = URIPath("data:application/octet-stream,%FF%FE")
    assert binary.read_bytes() == b"\xff\xfe"
    assert str(binary) == "data:application/octet-stream,%FF%FE"
