import contextlib
import functools
import http.server
import sys
import tempfile
import threading
import time

import pytest

import census as census_module
import hermetic
from server_loops import stop_server
from hermetic import NetworkAccessBlocked  # noqa: F401  (re-exported for tests)
from pathapi.mempath import MemPath, MemPathBackend

try:
    from hypothesis import settings as _hypothesis_settings
except ImportError:  # hypothesis is a dev extra
    pass
else:
    # A property that is slow on a busy runner is not a failure.
    _hypothesis_settings.register_profile("uripath", deadline=None)
    _hypothesis_settings.load_profile("uripath")


@pytest.fixture
def fixture_tree(tmp_path):
    """A small fixture tree for glob/walk/contract tests:

    root/
      a.txt
      b.py
      .hidden.txt
      sub/
        c.py
        nested/
          d.py
      empty_dir/

    Built by the shipped `pathapi.testing.populate_fixture_tree()`, so
    the in-repo contracts and downstream users share one definition.
    """
    from pathapi.testing import populate_fixture_tree

    return populate_fixture_tree(tmp_path)


@contextlib.contextmanager
def _serve_http(handler):
    """Run a `ThreadingHTTPServer` for `handler` on an OS-assigned loopback
    port; yields its base URL (no trailing slash) and stops it on exit."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    # A short poll interval: `shutdown()` waits up to one for the loop to see it.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def serve_http():
    """The `_serve_http(handler)` context manager, for tests that need a
    one-off handler of their own."""
    return _serve_http


def pytest_addoption(parser):
    parser.addoption(
        "--http-transports",
        default="builtin",
        help="the HTTP transports the transport suite runs against, by the "
        "names of pathapi.http.transport_names(), separated by commas "
        "(for example builtin,requests)",
    )
    parser.addoption(
        "--leak-census",
        nargs="?",
        const="report",
        choices=("report", "fail"),
        default=None,
        help="at the end of the session, list the sockets, event loops, "
        "subprocesses and threads still alive; `fail` also exits non-zero "
        "(add python -X tracemalloc=25 to name where each was created)",
    )


_SESSION = pytest.StashKey[object]()


def pytest_sessionstart(session):
    session.config.stash[_SESSION] = session


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    mode = config.getoption("--leak-census")
    if not mode:
        return
    census = census_module.take_census()
    terminalreporter.section("leak census")
    if not census.items:
        terminalreporter.write_line("nothing is still alive")
        return
    for line in census.lines():
        terminalreporter.write_line(line)
    terminalreporter.write_line(
        f"{len(census.items)} alive, {len(census.library_owned())} created by "
        "uripath (known only under -X tracemalloc)"
    )
    if mode == "fail" and exitstatus == 0:
        # The summary runs inside `pytest_sessionfinish`; the process exits
        # with the status the session holds afterwards.
        config.stash[_SESSION].exitstatus = 1


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_network: lift the autouse non-loopback network guard for a test "
        "that deliberately resolves or connects to a real host",
    )
    config.addinivalue_line(
        "markers",
        "allow_program(*names): let a test start these programs; any other "
        "except the interpreter and the host probes raises ProcessSpawnBlocked",
    )
    # The session's environment is set before the first test's snapshot of it
    # is taken, and put back when pytest exits.
    home = tempfile.TemporaryDirectory(prefix="uripath-home-")
    patch = pytest.MonkeyPatch()
    hermetic.isolate_environment(patch, home.name)
    config.add_cleanup(home.cleanup)
    config.add_cleanup(patch.undo)


_ENV_BEFORE = pytest.StashKey[dict]()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    item.stash[_ENV_BEFORE] = hermetic.environment_snapshot()
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    result = yield
    before = item.stash.get(_ENV_BEFORE, None)
    changed = (
        hermetic.changed_variables(before, hermetic.environment_snapshot())
        if before is not None
        else {}
    )
    if changed:
        hermetic.restore_environment(before)
        raise AssertionError(
            "the test left the process environment changed (use monkeypatch): "
            + ", ".join(f"{k}: {old!r} -> {new!r}" for k, (old, new) in changed.items())
        )
    return result


@pytest.fixture(autouse=True)
def _block_non_loopback_network(request, monkeypatch):
    """Hermetic tests: any connect/sendto/name lookup aimed at a host other
    than loopback raises `NetworkAccessBlocked`, a program other than the
    interpreter raises `ProcessSpawnBlocked`, and a blocked attempt fails the
    test at teardown even if the code under test swallowed the error.
    Autouse rather than opt-in, because the failure it prevents (a refactor
    that quietly sends a monkeypatched HTTP test to the real internet, or a
    DNS lookup that stalls an offline CI runner) is only caught by a guard
    the test author did not have to remember. `@pytest.mark.allow_network`
    lifts the network half for a test that means to use the network."""
    blocked = []
    if not request.node.get_closest_marker("allow_network"):
        hermetic.install_network_guard(monkeypatch, blocked)
    allowed = [
        name
        for marker in request.node.iter_markers("allow_program")
        for name in marker.args
    ]
    hermetic.install_process_guard(monkeypatch, blocked, allowed)
    # Yielded so a test of the guard itself can inspect and clear it.
    yield blocked
    if blocked:
        pytest.fail(f"non-loopback network access attempted: {blocked}")


@pytest.fixture(autouse=True)
def _close_cached_ftp_connections():
    """The FTP connection cache outlives a test, but the loopback server a
    test started does not: close what the test left in it, so no socket
    waits for the interpreter to exit."""
    yield
    import sys

    ftp = sys.modules.get("pathapi.ftp._backend")
    if ftp is not None:
        for key in list(ftp._CACHED_CLIENTS.cache):
            ftp._CACHED_CLIENTS.discard(*key)


@pytest.fixture
def mem_backend():
    return MemPathBackend()


@pytest.fixture
def mem_root(mem_backend):
    return MemPath("/", backend=mem_backend)


def pytest_generate_tests(metafunc):
    if "http_transport_kind" in metafunc.fixturenames:
        kinds = [
            name.strip()
            for name in metafunc.config.getoption("--http-transports").split(",")
            if name.strip()
        ]
        metafunc.parametrize("http_transport_kind", kinds, indirect=True)


@pytest.fixture
def http_transport_kind(request, monkeypatch):
    """Runs the test once per HTTP transport (`--http-transports`): the
    default transport of every backend the test builds is that kind
    (`PATHAPI_HTTP_TRANSPORT`), and `http_fakes.make_transport(kind)` builds
    one of it."""
    monkeypatch.setenv("PATHAPI_HTTP_TRANSPORT", request.param)
    return request.param


@pytest.fixture
def http_transport(http_transport_kind):
    """A transport of the kind under test, closed after the test."""
    from http_fakes import make_transport

    with make_transport(http_transport_kind) as transport:
        yield transport


@pytest.fixture
def http_server(fixture_tree):
    """Serve fixture_tree over HTTP via stdlib's ThreadingHTTPServer with
    directory-listing support, on an OS-assigned port. Yields the base URL
    (no trailing slash)."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(fixture_tree)
    )
    with _serve_http(handler) as base_url:
        yield base_url


class _CannedListingHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with `list_directory()` overridden to emit
    Apache-`<pre>`- or nginx-`<table>`-style listing HTML instead of the
    stdlib's bare `<ul><li>` -- the real `http_server` fixture never
    exercises `_DirectoryListingParser`'s two primary (non-fallback) code
    paths at all, since SimpleHTTPRequestHandler only ever emits `<ul>`.
    File GET/HEAD/redirect behavior is inherited unchanged from the stdlib
    handler; only the directory-index HTML differs. `listing_format` is a
    class attr set per-fixture via subclassing (not `functools.partial`,
    since we need to override a method, not just bind __init__ args)."""

    listing_format = "pre"  # or "table"

    def list_directory(self, path):
        import io
        import os
        import urllib.parse

        try:
            entries = os.listdir(path)
        except OSError:
            self.send_error(404, "No permission to list directory")
            return None
        entries.sort(key=lambda a: a.lower())

        rows = []
        for name in entries:
            fullname = os.path.join(path, name)
            is_dir = os.path.isdir(fullname)
            displayname = name + ("/" if is_dir else "")
            href = urllib.parse.quote(displayname)
            st = os.stat(fullname)
            mtime = time.strftime("%d-%b-%Y %H:%M:%S", time.localtime(st.st_mtime))
            size = "-" if is_dir else str(st.st_size)
            if self.listing_format == "pre":
                pad = " " * max(1, 45 - len(displayname))
                rows.append(f'<a href="{href}">{displayname}</a>{pad}{mtime}  {size}\n')
            else:
                rows.append(
                    f'<tr><td><a href="{href}">{displayname}</a></td>'
                    f'<td>{mtime}</td><td align="right">{size}</td>'
                    f"<td>&nbsp;</td></tr>\n"
                )
        body = "".join(rows)

        title = f"Index of {self.path}"
        if self.listing_format == "pre":
            html = (
                f"<html><head><title>{title}</title></head><body>"
                f'<h1>{title}</h1><pre><a href="../">../</a>\n{body}</pre>'
                "</body></html>"
            )
        else:
            head = (
                '<tr><th><a href="?C=N;O=D">Name</a></th>'
                '<th><a href="?C=M;O=A">Last modified</a></th>'
                '<th><a href="?C=S;O=A">Size</a></th><th>Description</th></tr>\n'
                '<tr><th colspan="4"><hr></th></tr>\n'
            )
            parent = (
                '<tr><td><a href="../">Parent Directory</a></td>'
                '<td>&nbsp;</td><td align="right">-</td><td>&nbsp;</td></tr>\n'
            )
            html = (
                f"<html><head><title>{title}</title></head><body>"
                f"<h1>{title}</h1><table>\n{head}{parent}{body}"
                "</table></body></html>"
            )

        encoded = html.encode("utf-8", "surrogateescape")
        f = io.BytesIO(encoded)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def log_message(self, format, *args):
        pass


class _ApachePreListingHandler(_CannedListingHandler):
    listing_format = "pre"


class _NginxTableListingHandler(_CannedListingHandler):
    listing_format = "table"


def _start_canned_server(handler_cls, fixture_tree):
    handler = functools.partial(handler_cls, directory=str(fixture_tree))
    with _serve_http(handler) as base_url:
        yield base_url


@pytest.fixture
def http_server_apache_pre(fixture_tree):
    """Like `http_server`, but directory listings are Apache
    `mod_autoindex`-style `<pre>` HTML -- drives
    `_DirectoryListingParser`'s `<pre>` code path end-to-end."""
    yield from _start_canned_server(_ApachePreListingHandler, fixture_tree)


@pytest.fixture
def http_server_nginx_table(fixture_tree):
    """Like `http_server`, but directory listings are nginx
    `autoindex`-style `<table>` HTML -- drives
    `_DirectoryListingParser`'s `<table>` code path end-to-end."""
    yield from _start_canned_server(_NginxTableListingHandler, fixture_tree)


@pytest.fixture
def http_status_server():
    """Serves canned status codes / delays on demand, driving
    `_translate_http_errors` from real `requests` exceptions instead of
    hand-constructed ones: GET/HEAD/PUT/DELETE `/<code>` returns that
    status; `/timeout` sleeps past any client-side timeout. Yields the
    base URL (no trailing slash)."""

    class _StatusHandler(http.server.BaseHTTPRequestHandler):
        def _handle(self):
            path = self.path.lstrip("/")
            if path == "timeout":
                time.sleep(5)
                return
            try:
                code = int(path)
            except ValueError:
                code = 404
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_HEAD = do_PUT = do_DELETE = _handle

        def log_message(self, format, *args):
            pass

    with _serve_http(_StatusHandler) as base_url:
        yield base_url


class _WritableHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler + real PUT/DELETE/PATCH against files on disk --
    for a genuine write-then-read-back round trip. Existing
    `test_http_write_*`/`test_http_unlink` tests only monkeypatch
    `requests.Session.request` and assert the request was sent; they never
    verify data actually persists server-side."""

    def do_PUT(self):
        import pathlib

        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        p = pathlib.Path(self.translate_path(self.path))
        existed = p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        self.send_response(204 if existed else 201)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PATCH(self):
        """Handle PATCH with Content-Range header for append mode."""
        import pathlib
        import re

        content_range = self.headers.get("Content-Range", "")
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)
        p = pathlib.Path(self.translate_path(self.path))

        # Parse Content-Range: bytes start-end/*
        match = re.match(r"bytes (\d+)-(\d+)/\*", content_range)
        if not match:
            self.send_error(400, "Invalid Content-Range header")
            return

        start = int(match.group(1))
        end = int(match.group(2))

        # Ensure parent exists
        p.parent.mkdir(parents=True, exist_ok=True)

        # Read existing content or start with empty
        if p.exists():
            existing = p.read_bytes()
        else:
            existing = b""

        # Append at the specified offset
        if start > len(existing):
            # Pad with zeros if start is beyond current size
            new_content = existing + (b"\x00" * (start - len(existing))) + data
        else:
            # Replace/append at the given offset
            new_content = existing[:start] + data

        p.write_bytes(new_content)
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        import pathlib

        p = pathlib.Path(self.translate_path(self.path))
        if not p.exists():
            self.send_error(404)
            return
        p.unlink()
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        pass


class _HeadRejectingHandler(http.server.SimpleHTTPRequestHandler):
    """GET works normally; HEAD always 405s -- drives `stat()`'s
    HEAD-405-fallback-to-GET path against a real server."""

    def do_HEAD(self):
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def http_writable_server(fixture_tree):
    yield from _start_canned_server(_WritableHandler, fixture_tree)


@pytest.fixture
def http_server_head_rejecting(fixture_tree):
    yield from _start_canned_server(_HeadRejectingHandler, fixture_tree)


@pytest.fixture
def unused_tcp_port():
    """A port nobody is listening on, for connection-refused coverage."""
    import netimps

    return netimps.get_free_port()


@pytest.fixture
def ftp_server(fixture_tree):
    pytest.importorskip("pyftpdlib")
    import errno
    import threading
    import warnings

    with warnings.catch_warnings():
        # pyftpdlib still imports asyncore/asynchat on Python 3.10/3.11,
        # which we don't control and which should not fail our own test
        # suite under global "warnings as errors".
        warnings.filterwarnings(
            "ignore",
            message=r".*asyncore module is deprecated.*",
            category=DeprecationWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r".*asynchat module is deprecated.*",
            category=DeprecationWarning,
        )
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.ioloop import Select
        from pyftpdlib.servers import FTPServer

    # pyftpdlib's MFMT calls datetime.utcfromtimestamp(), deprecated since
    # 3.12: under "warnings as errors" its server thread would raise and drop
    # the connection. The filter lasts for the test that uses the fixture.
    warnings.filterwarnings(
        "ignore",
        message=r".*utcfromtimestamp.*",
        category=DeprecationWarning,
    )

    authorizer = DummyAuthorizer()
    authorizer.add_user("user", "12345", str(fixture_tree), perm="elradfmwMT")

    class Handler(FTPHandler):
        pass

    Handler.authorizer = authorizer
    handler = Handler
    # Force the portable select-based loop for tests. pyftpdlib's macOS
    # kqueue loop can emit an unhandled thread exception if the server fd is
    # closed from the pytest thread while the server thread is polling it.
    ioloop = Select()
    server = FTPServer(("127.0.0.1", 0), handler, ioloop=ioloop)

    stop = threading.Event()

    def serve():
        # serve_forever()'s own loop, with a poll timeout and a stop flag:
        # without a timeout select() blocks indefinitely, so a close
        # scheduled from the pytest thread never ran and every teardown
        # waited out its full join timeout. Everything, close_all()
        # included, runs on this thread.
        try:
            while not stop.is_set() and ioloop.socket_map:
                ioloop.poll(0.05)
                ioloop.sched.poll()
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
        finally:
            server.close_all()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        port = server.socket.getsockname()[1]
        yield f"ftp://user:12345@127.0.0.1:{port}/"
    finally:
        stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive(), "ftp_server thread did not stop"


@pytest.fixture
def dav_server(fixture_tree):
    import time
    import threading

    pytest.importorskip("wsgidav")
    pytest.importorskip("cheroot")
    import wsgidav.wsgidav_app
    from cheroot import wsgi

    config = {
        "host": "127.0.0.1",
        "port": 0,
        "provider_mapping": {"/": str(fixture_tree)},
        "simple_dc": {"user_mapping": {"*": True}},
        "logging": {"enable": False},
    }
    app = wsgidav.wsgidav_app.WsgiDAVApp(config)
    server = wsgi.Server(("127.0.0.1", 0), app)
    thread = threading.Thread(target=server.start, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.ready:
        assert thread.is_alive(), "dav_server thread died while starting"
        assert time.monotonic() < deadline, "dav_server did not become ready"
        time.sleep(0.01)
    try:
        yield f"dav://127.0.0.1:{server.bind_addr[1]}"
    finally:
        server.stop()
        thread.join(timeout=5)
