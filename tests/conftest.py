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
from pathlib_next.mempath import MemPath, MemPathBackend


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

    Built by the shipped `pathlib_next.testing.populate_fixture_tree()`, so
    the in-repo contracts and downstream users share one definition.
    """
    from pathlib_next.testing import populate_fixture_tree

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

    ftp = sys.modules.get("pathlib_next.ftp._backend")
    if ftp is not None:
        for key in list(ftp._CACHED_CLIENTS.cache):
            ftp._CACHED_CLIENTS.discard(*key)


@pytest.fixture
def mem_backend():
    return MemPathBackend()


@pytest.fixture
def mem_root(mem_backend):
    return MemPath("/", backend=mem_backend)


TRANSPORT_KINDS = ["builtin"]


@pytest.fixture(params=TRANSPORT_KINDS)
def http_transport_kind(request, monkeypatch):
    """Runs the test once per HTTP transport: the default transport of every
    backend the test builds is that kind (`PATHLIB_NEXT_HTTP_TRANSPORT`), and
    `http_fakes.make_transport(kind)` builds one of it."""
    monkeypatch.setenv("PATHLIB_NEXT_HTTP_TRANSPORT", request.param)
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


def _build_git_tree(local_dir):
    """Flatten a local directory into a git-tree-shaped {posix relpath:
    bytes} dict for the fake GitHub/GitLab servers below. Git has no
    concept of an empty directory (no tree entry can represent one with no
    blobs under it) -- a truly empty dir (fixture_tree's `empty_dir/`)
    would vanish from any listing derived purely from blob-path prefixes,
    so a `.gitkeep`-style placeholder blob is synthesized under it here,
    same as a real repo author would have to do. This only affects the
    fake server's in-memory tree, never `fixture_tree` itself."""
    import pathlib

    local_dir = pathlib.Path(local_dir)
    tree = {}
    for path in sorted(local_dir.rglob("*")):
        rel = path.relative_to(local_dir).as_posix()
        if path.is_dir():
            if not any(path.iterdir()):
                tree[f"{rel}/.gitkeep"] = b""
        else:
            tree[rel] = path.read_bytes()
    return tree


def _git_tree_children(tree, prefix):
    """Immediate children of `prefix` ("" for root) in a `_build_git_tree`
    dict -- name -> "dir"/"file", mirroring how GitHub's contents API and
    GitLab's tree API both report one directory level at a time."""
    prefix = f"{prefix}/" if prefix else ""
    children = {}
    for key in tree:
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix) :]
        if not rest:
            continue
        name, sep, _ = rest.partition("/")
        children[name] = "dir" if sep else "file"
    return children


@pytest.fixture
def github_api_server(fixture_tree):
    """Faithful (not mocked) fake of the subset of the GitHub REST contents
    API (`GET /repos/{owner}/{repo}/contents/{path}`) that `GitHubPath`
    actually calls: directory listing (JSON array), file metadata
    (JSON object, base64 `content`), and raw file bodies (`Accept:
    .../vnd.github.raw+json`). A `HEAD` gets the headers of the `GET`, and
    every reply names its media type in `X-GitHub-Media-Type`. Two refs are served (`main` the default,
    `other-branch` with a divergent `a.txt`) so ref plumbing is verified
    end-to-end, not just default-branch reads. Like the real API, a
    contents listing stops at 1,000 entries with no truncation signal; the
    Git Trees API (`GET /repos/{owner}/{repo}/git/trees/{sha}`, `sha` from a
    listing entry or a ref name for the root) and `GET /repos/{owner}/{repo}`
    (`default_branch`) are served for the uncapped route. The tree is read
    from `fixture_tree` on every request, so a test may add files first.
    Yields `(base_url, owner, repo)`."""
    import base64
    import hashlib
    import json
    import urllib.parse

    owner, repo = "acme", "widgets"

    def _refs():
        main_tree = _build_git_tree(fixture_tree)
        other_tree = dict(main_tree)
        other_tree["a.txt"] = b"a-on-other-branch"
        return {"main": main_tree, "other-branch": other_tree}

    def _dir_sha(ref, path):
        return hashlib.sha1(f"{ref}:{path}".encode()).hexdigest()

    class _GitHubApiHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            # The headers of the GET and no body, as the API answers.
            self.do_GET()

        def _media_type(self):
            raw = "raw" in self.headers.get("Accept", "")
            return (
                "github.v3; param=raw; format=json" if raw else "github.v3; format=json"
            )

        def do_GET(self):
            split = urllib.parse.urlsplit(self.path)
            qs = urllib.parse.parse_qs(split.query)
            refs = _refs()

            if split.path == f"/repos/{owner}/{repo}":
                self._send_json(200, {"default_branch": "main"})
                return
            trees = f"/repos/{owner}/{repo}/git/trees/"
            if split.path.startswith(trees):
                self._send_tree(refs, urllib.parse.unquote(split.path[len(trees) :]))
                return

            ref = qs.get("ref", ["main"])[0]
            tree = refs.get(ref)
            if tree is None:
                self._send_json(404, {"message": "Not Found"})
                return

            prefix = f"/repos/{owner}/{repo}/contents"
            if split.path == prefix:
                subpath = ""
            elif split.path.startswith(prefix + "/"):
                subpath = urllib.parse.unquote(split.path[len(prefix) + 1 :])
            else:
                self._send_json(404, {"message": "Not Found"})
                return

            if subpath in tree:
                self._send_file(subpath, tree[subpath])
                return

            children = _git_tree_children(tree, subpath)
            if children or subpath == "":
                entries = []
                for name, kind in sorted(children.items()):
                    childpath = f"{subpath}/{name}" if subpath else name
                    size = len(tree.get(childpath, b"")) if kind == "file" else 0
                    entries.append(
                        {
                            "name": name,
                            "path": childpath,
                            "type": kind,
                            "size": size,
                            "sha": _dir_sha(ref, childpath) if kind == "dir" else None,
                        }
                    )
                self._send_json(200, entries[:1000])
                return

            self._send_json(404, {"message": "Not Found"})

        def _send_tree(self, refs, sha):
            for ref, tree in refs.items():
                dirs = {""}
                for key in tree:
                    parts = key.split("/")[:-1]
                    dirs.update("/".join(parts[: i + 1]) for i in range(len(parts)))
                for path in dirs:
                    if (path == "" and sha == ref) or (
                        path and sha == _dir_sha(ref, path)
                    ):
                        entries = []
                        for name, kind in sorted(
                            _git_tree_children(tree, path).items()
                        ):
                            childpath = f"{path}/{name}" if path else name
                            entry = {"path": name, "mode": "100644"}
                            if kind == "dir":
                                entry.update(type="tree", sha=_dir_sha(ref, childpath))
                            else:
                                entry.update(type="blob", size=len(tree[childpath]))
                            entries.append(entry)
                        self._send_json(
                            200, {"sha": sha, "tree": entries, "truncated": False}
                        )
                        return
            self._send_json(404, {"message": "Not Found"})

        def _send_file(self, subpath, content):
            accept = self.headers.get("Accept", "")
            if "raw" in accept:
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/vnd.github.raw+json; charset=utf-8"
                )
                self.send_header("Content-Length", str(len(content)))
                self.send_header("X-GitHub-Media-Type", self._media_type())
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(content)
                return
            self._send_json(
                200,
                {
                    "name": subpath.rsplit("/", 1)[-1],
                    "path": subpath,
                    "type": "file",
                    "size": len(content),
                    "encoding": "base64",
                    "content": base64.b64encode(content).decode(),
                },
            )

        def _send_json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-GitHub-Media-Type", self._media_type())
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    with _serve_http(_GitHubApiHandler) as base_url:
        yield base_url, owner, repo


@pytest.fixture
def gitlab_api_server(fixture_tree):
    """Faithful (not mocked) fake of the subset of the GitLab REST API v4
    that `GitLabPath` actually calls: `.../repository/tree` (listing, no
    size -- matches the real endpoint's shape), `.../repository/files/:path`
    (file metadata) and `.../repository/files/:path/raw` (file body). Like
    the real API, the tree listing is paginated (`per_page` capped at 100,
    `page`, `X-Next-Page`), lists trees before blobs, 404s an unknown
    project, ref or tree path; only the `main` ref exists. The same tree is
    also served as the subgroup project `acme/team/widgets`. The tree is
    read from `fixture_tree` on every request, so a test may add files
    first. Yields `(base_url, owner, repo)`."""
    import json
    import urllib.parse

    owner, repo = "acme", "widgets"
    project_ids = [
        urllib.parse.quote(f"{owner}/{repo}", safe=""),
        urllib.parse.quote(f"{owner}/team/{repo}", safe=""),
    ]

    class _GitLabApiHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            split = urllib.parse.urlsplit(self.path)
            qs = urllib.parse.parse_qs(split.query)
            tree = _build_git_tree(fixture_tree)

            # `GET /projects/:id` (default_branch lookup) -- no "/repository/"
            # suffix, must be checked before the repository-scoped prefix below.
            if split.path in [f"/api/v4/projects/{pid}" for pid in project_ids]:
                self._send_json(200, {"default_branch": "main"})
                return

            for project_id in project_ids:
                prefix = f"/api/v4/projects/{project_id}/repository/"
                if split.path.startswith(prefix):
                    break
            else:
                self._send_json(404, {"message": "404 Project Not Found"})
                return
            rest = split.path[len(prefix) :]
            if qs.get("ref", ["main"])[0] != "main":
                self._send_json(404, {"message": "404 Tree Not Found"})
                return

            if rest == "tree":
                path = qs.get("path", [""])[0]
                children = _git_tree_children(tree, path)
                if path and not children:
                    self._send_json(404, {"message": "404 Tree Not Found"})
                    return
                entries = [
                    {
                        "id": f"fake-{name}",
                        "name": name,
                        "type": "tree" if kind == "dir" else "blob",
                        "path": f"{path}/{name}" if path else name,
                        "mode": "040000" if kind == "dir" else "100644",
                    }
                    for name, kind in sorted(
                        children.items(), key=lambda item: (item[1] != "dir", item[0])
                    )
                ]
                per_page = min(int(qs.get("per_page", ["20"])[0]), 100)
                page = int(qs.get("page", ["1"])[0])
                chunk = entries[(page - 1) * per_page : page * per_page]
                has_next = page * per_page < len(entries)
                self._send_json(
                    200, chunk, {"X-Next-Page": str(page + 1) if has_next else ""}
                )
                return

            if rest.startswith("files/"):
                filerest = rest[len("files/") :]
                raw = filerest.endswith("/raw")
                encoded_path = filerest[: -len("/raw")] if raw else filerest
                path = urllib.parse.unquote(encoded_path)
                # Real GitLab requires `ref` on the files endpoints (both
                # metadata and /raw) -- omitting it is a 400, not a
                # default-branch fallback like the tree endpoint gets
                # (confirmed live against gitlab.com; GitLabPath resolves
                # and sends it, this just mirrors the real requirement).
                if "ref" not in qs:
                    self._send_json(400, {"error": "ref is missing, ref is empty"})
                    return
                content = tree.get(path)
                if content is None:
                    self._send_json(404, {"message": "404 File Not Found"})
                    return
                if raw:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(content)
                    return
                self._send_json(
                    200,
                    {
                        "file_name": path.rsplit("/", 1)[-1],
                        "file_path": path,
                        "size": len(content),
                    },
                    # The files endpoint describes the file in headers too,
                    # and answers HEAD with those headers alone.
                    {"X-Gitlab-Size": str(len(content))},
                )
                return

            self._send_json(404, {"message": "404 Not Found"})

        do_HEAD = do_GET

        def _send_json(self, status, payload, headers=None):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    with _serve_http(_GitLabApiHandler) as base_url:
        yield base_url, owner, repo
