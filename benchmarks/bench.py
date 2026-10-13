"""uripath benchmark runner.

Run `python benchmarks/bench.py --help` for the options. `--save` writes the
run as structured JSON into `benchmarks/results/`; the schema is documented in
`benchmarks/README.md`.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sysconfig
import timeit
import tempfile
import functools
import http.server
import threading
import datetime
from pathlib import Path as StdlibPath

# Add src to sys.path so we can import uripath without installing it
import sys

REPO_ROOT = StdlibPath(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from uripath import Uri

SCHEMA = "uripath.bench/1"
MAX_SAMPLES = 100


class _Recorder:
    """Collects every measured metric of one run for `--save`.

    A timing metric stores min/median/max milliseconds per call over its
    samples; each sample times `calls_per_sample` calls of the operation.
    """

    def __init__(self):
        self.metrics = {}
        self.counters = {}
        self.errors = {}
        self.skipped = {}

    def timing(self, name, samples, *, group, calls=1):
        per_call_ms = sorted(sample / calls * 1000.0 for sample in samples)
        self.metrics[name] = {
            "group": group,
            "min_ms": round(per_call_ms[0], 6),
            "median_ms": round(statistics.median(per_call_ms), 6),
            "max_ms": round(per_call_ms[-1], 6),
            "samples": len(per_call_ms),
            "calls_per_sample": calls,
        }

    def counter(self, name, values, *, group):
        self.counters[name] = {"group": group, **values}

    def error(self, name, message, *, group):
        self.errors[name] = {"group": group, "error": message}

    def skip(self, name, reason, *, group):
        self.skipped[name] = {"group": group, "reason": reason}


RECORDER = _Recorder()
_SAMPLES_OVERRIDE = None


def _reps(default):
    """Sample count for a case: `--samples` when given, else the case default."""
    return _SAMPLES_OVERRIDE or default


def _timeit(stmt, *, number, name, group, setup="pass", repeat=5):
    """`timeit.repeat` a statement, record it, return the median sample total."""
    samples = timeit.repeat(stmt, setup=setup, number=number, repeat=_reps(repeat))
    RECORDER.timing(name, samples, group=group, calls=number)
    return statistics.median(samples)


def benchmark_uri_parse():
    # Parse a typical complex URI 10,000 times
    setup = "from uripath import Uri"
    code = "Uri('http://user:pass@host:80/path/to/resource?query=1#fragment')"
    return _timeit(
        code,
        setup=setup,
        number=10000,
        name="uri: Uri() construct, same literal",
        group="uri",
    )


def benchmark_uri_parse_unique():
    # Uri() construction is lazy (no parsing until .source/.path/... is
    # first accessed) and benchmark_uri_parse() above reuses the SAME
    # literal string every call, so it measures neither real parse cost.
    # This one forces the actual parse (the one-pass
    # _parse_uri) with a UNIQUE URI per iteration -- repeated-URI
    # microbenchmarks are not representative of real workloads and can
    # flatter/mislead by an order of magnitude if the underlying string
    # library caches by input (verified true of urllib.urlsplit, ~28x;
    # not true of uritools/our own parser, but always bench unique inputs
    # regardless so this stays an apples-to-apples comparison).
    from uripath import Uri

    n = 5000
    urls = [
        f"http://user:pass@host{i}.example.com:8080"
        f"/path/to/resource{i}?query={i}#fragment{i}"
        for i in range(n)
    ]

    def _run():
        for url in urls:
            u = Uri(url)
            _ = u.source
            _ = u.path
            _ = u.query
            _ = u.fragment

    samples = timeit.repeat(_run, number=1, repeat=_reps(5))
    RECORDER.timing("uri: parse, unique URIs, forced", samples, group="uri", calls=n)
    return statistics.median(samples) / n * 1e6  # microseconds per unique Uri() parse


def benchmark_uri_parse_and_compose_unique():
    # Full round trip: parse (forced, unique URIs) + compose (as_uri(),
    # uncached -- sanitize=True forces a fresh compose every call instead
    # of hitting the cached-after-first-call fast path) -- exercises both
    # the one-pass parse (_parse_uri) and direct-assembly compose
    # (_format_parsed_parts) together, which is what "Uri() construction"
    # means end to end.
    from uripath import Uri

    n = 5000
    urls = [
        f"http://user:pass@host{i}.example.com:8080"
        f"/path/to/resource{i}?query={i}#fragment{i}"
        for i in range(n)
    ]

    def _run():
        for url in urls:
            u = Uri(url)
            _ = u.as_uri(sanitize=True)

    samples = timeit.repeat(_run, number=1, repeat=_reps(5))
    RECORDER.timing("uri: parse+compose, unique URIs", samples, group="uri", calls=n)
    return (
        statistics.median(samples) / n * 1e6
    )  # microseconds per unique Uri() parse+compose


def benchmark_path_join():
    # Join paths using / operator 10,000 times
    setup = "from uripath import Uri; p = Uri('http://host/path')"
    code = "p / 'sub' / 'child'"
    return _timeit(code, setup=setup, number=10000, name="uri: path join", group="uri")


def benchmark_segments_name_access():
    # Access .segments and .name 10,000 times
    setup = "from uripath import Uri; u = Uri('http://host/a/b/c/d/e')"
    code = "_ = u.segments; _ = u.name"
    return _timeit(
        code, setup=setup, number=10000, name="uri: segments + name access", group="uri"
    )


def benchmark_suffix_stem():
    # Access .suffix and .stem 10,000 times
    setup = "from uripath import Uri; u = Uri('http://host/path/file.tar.gz')"
    code = "_ = u.suffix; _ = u.stem"
    return _timeit(
        code, setup=setup, number=10000, name="uri: suffix + stem access", group="uri"
    )


def benchmark_walk_glob_http():
    # Set up a small temp directory for HTTP server
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = StdlibPath(tmpdir)
        # Create a small tree (20 files)
        for i in range(4):
            sub = tmp_path / f"dir_{i}"
            sub.mkdir()
            for j in range(5):
                (sub / f"file_{j}.html").write_text("data")

        class QuietSimpleHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                return

        handler = functools.partial(
            QuietSimpleHTTPRequestHandler, directory=str(tmp_path)
        )
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            # We import the HttpPath scheme
            from uripath.schemes.http import HttpPath

            url = f"http://127.0.0.1:{port}"

            # Warm up
            hp = HttpPath(url)
            _ = list(hp.glob("**/*.html"))

            # Benchmark glob and walk, 10 calls per sample
            glob_samples = timeit.repeat(
                lambda: list(hp.glob("**/*.html")), number=10, repeat=_reps(3)
            )
            RECORDER.timing(
                "http: HttpPath glob('**/*.html') 20 files",
                glob_samples,
                group="http",
                calls=10,
            )
            walk_samples = timeit.repeat(
                lambda: list(hp.walk()), number=10, repeat=_reps(3)
            )
            RECORDER.timing(
                "http: HttpPath walk() 20 files", walk_samples, group="http", calls=10
            )

            _benchmark_http_transports(url)

            return statistics.median(glob_samples), statistics.median(walk_samples)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _benchmark_http_transports(url):
    """The same listing work and a run of small GETs on the transport
    `HTTPTransport` (the default above)."""
    from uripath.schemes.http import HttpPath, HTTPTransport

    transports = [("builtin", HTTPTransport)]
    for name, make in transports:
        transport = make()
        try:
            root = HttpPath(url).with_transport(transport)
            list(root.walk())  # warm up
            walk_samples = timeit.repeat(
                lambda: list(root.walk()), number=10, repeat=_reps(3)
            )
            RECORDER.timing(
                f"http: HttpPath walk() 20 files, {name} transport",
                walk_samples,
                group="http",
                calls=10,
            )
            target = root / "dir_0" / "file_0.html"
            target.read_bytes()
            get_samples = timeit.repeat(
                lambda: [target.read_bytes() for _ in range(50)],
                number=1,
                repeat=_reps(3),
            )
            RECORDER.timing(
                f"http: 50 GETs of one small file, {name} transport",
                get_samples,
                group="http",
                calls=50,
            )
        finally:
            transport.close()


def benchmark_http_directory_parser():
    # benchmark_walk_glob_http() above serves fixture files through stdlib
    # SimpleHTTPRequestHandler, whose listing is a bare <ul><li> -- that
    # only ever exercises _DirectoryListingParser's `all_links` fallback
    # branch, never its two primary (and far more common in the real
    # world) Apache-<pre>/nginx-<table> code paths. This benchmarks those
    # directly against realistic synthetic HTML (during the replacement
    # work this in-house parser was verified equivalent to, and 2.9x-6.2x faster
    # than, the bs4+html5lib+htmllistparse implementation it replaced).
    from uripath.schemes.http import _DirectoryListingParser

    def make_apache_pre(n):
        rows = ['<a href="../">../</a>\n']
        for i in range(n):
            is_dir = i % 7 == 0
            name = f"dir_{i}/" if is_dir else f"file_{i:04d}.txt"
            size = "-" if is_dir else f"{(i % 900) + 1}.{i % 10}K"
            rows.append(
                f'<a href="{name}">{name}</a>'
                + " " * max(1, 50 - len(name))
                + f"11-Jul-2026 10:{i % 60:02d}:00    {size}\n"
            )
        body = "".join(rows)
        return (
            "<html><head><title>Index of /files/</title></head><body>"
            "<h1>Index of /files/</h1><pre>" + body + "</pre></body></html>"
        )

    def make_nginx_table(n):
        head = (
            '<tr><th><a href="?C=N;O=D">Name</a></th>'
            '<th><a href="?C=M;O=A">Last modified</a></th>'
            '<th><a href="?C=S;O=A">Size</a></th><th>Description</th></tr>\n'
            '<tr><th colspan="4"><hr></th></tr>\n'
            '<tr><td><a href="/files/">Parent Directory</a></td>'
            '<td>&nbsp;</td><td align="right">-</td><td>&nbsp;</td></tr>\n'
        )
        rows = [head]
        for i in range(n):
            is_dir = i % 7 == 0
            name = f"dir_{i}/" if is_dir else f"file_{i:04d}.txt"
            size = "-" if is_dir else f"{(i % 900) + 1}.{i % 10}K"
            rows.append(
                f'<tr><td><a href="{name}">{name}</a></td>'
                f"<td>2026-07-11 10:{i % 60:02d}  </td>"
                f'<td align="right">{size}</td><td>&nbsp;</td></tr>\n'
            )
        body = "".join(rows)
        return (
            "<html><head><title>Index of /files/</title></head><body>"
            "<h1>Index of /files/</h1><table>\n" + body + "</table></body></html>"
        )

    def parse(html):
        parser = _DirectoryListingParser()
        parser.feed(html)
        parser.close()
        return parser.listing

    n = 1000
    pre_html = make_apache_pre(n)
    table_html = make_nginx_table(n)
    pre_samples = timeit.repeat(lambda: parse(pre_html), number=20, repeat=_reps(3))
    table_samples = timeit.repeat(lambda: parse(table_html), number=20, repeat=_reps(3))
    RECORDER.timing(
        "http: listing parse, Apache <pre>, 1000 entries",
        pre_samples,
        group="http",
        calls=20,
    )
    RECORDER.timing(
        "http: listing parse, nginx <table>, 1000 entries",
        table_samples,
        group="http",
        calls=20,
    )
    # ms/parse, n=1000 entries
    return (
        statistics.median(pre_samples) / 20 * 1000,
        statistics.median(table_samples) / 20 * 1000,
    )


def main():
    print("Running benchmarks...")

    t_uri_parse = benchmark_uri_parse()
    print(f"1. URI Parse (10k runs): {t_uri_parse:.4f}s")

    t_uri_parse_unique = benchmark_uri_parse_unique()
    print(f"1b. URI Parse, unique URIs, forced (us/parse): {t_uri_parse_unique:.2f}us")

    t_uri_parse_compose_unique = benchmark_uri_parse_and_compose_unique()
    print(
        f"1c. URI Parse+Compose, unique URIs (us/round-trip): {t_uri_parse_compose_unique:.2f}us"
    )

    t_join = benchmark_path_join()
    print(f"2. Path Join (10k runs): {t_join:.4f}s")

    t_seg_name = benchmark_segments_name_access()
    print(f"3. Segments/Name Access (10k runs): {t_seg_name:.4f}s")

    t_suffix_stem = benchmark_suffix_stem()
    print(f"3b. Suffix/Stem Access (10k runs): {t_suffix_stem:.4f}s")

    t_http_glob, t_http_walk = benchmark_walk_glob_http()
    print(f"4. HTTP Glob (10 runs): {t_http_glob:.4f}s")
    print(f"5. HTTP Walk (10 runs): {t_http_walk:.4f}s")

    t_parser_pre, t_parser_table = benchmark_http_directory_parser()
    print(
        f"6. HTTP dir listing parse, Apache <pre>, n=1000 (ms/parse): {t_parser_pre:.4f}ms"
    )
    print(
        f"7. HTTP dir listing parse, nginx <table>, n=1000 (ms/parse): {t_parser_table:.4f}ms"
    )

    # Print Markdown table format for copy-pasting
    print("\n| Benchmark Case | Time / Metric |")
    print("|---|---|")
    print(f"| URI Parse (10k) | {t_uri_parse:.4f}s |")
    print(f"| URI Parse, unique URIs, forced (us/parse) | {t_uri_parse_unique:.2f}us |")
    print(
        f"| URI Parse+Compose, unique URIs (us/round-trip) | {t_uri_parse_compose_unique:.2f}us |"
    )
    print(f"| Path Join (10k) | {t_join:.4f}s |")
    print(f"| Segments/Name Access (10k) | {t_seg_name:.4f}s |")
    print(f"| Suffix/Stem Access (10k) | {t_suffix_stem:.4f}s |")
    print(f"| HTTP Glob (10) | {t_http_glob:.4f}s |")
    print(f"| HTTP Walk (10) | {t_http_walk:.4f}s |")
    print(
        f"| HTTP dir listing parse, Apache <pre> (n=1000) | {t_parser_pre:.4f}ms/parse |"
    )
    print(
        f"| HTTP dir listing parse, nginx <table> (n=1000) | {t_parser_table:.4f}ms/parse |"
    )


def _pyproject_version():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def _git_state():
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout.strip()

    try:
        commit = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        return None
    return {"commit": commit, "dirty": dirty}


def _interpreter_tag():
    """`<major.minor>-<os>-<arch>`, with the arch the interpreter was built for."""
    arch = sysconfig.get_platform().rsplit("-", 1)[-1]
    os_name = "darwin" if sys.platform == "darwin" else os.name
    return f"{sys.version_info[0]}.{sys.version_info[1]}-{os_name}-{arch}"


def build_result(suite, *, name, note=None):
    """The JSON document `--save` writes (schema: benchmarks/README.md)."""
    return {
        "schema": SCHEMA,
        "name": name,
        "suite": suite,
        "source": "ci" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
        "note": note,
        "created_utc": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "package": {"name": "uripath", "version": _pyproject_version()},
        "git": _git_state(),
        "python": f"{platform.python_implementation()} {platform.python_version()}",
        "interpreter": _interpreter_tag(),
        "processor": f"{platform.system()}-{platform.machine()}",
        "cpu_count": os.cpu_count(),
        "metrics": dict(sorted(RECORDER.metrics.items())),
        "counters": dict(sorted(RECORDER.counters.items())),
        "errors": dict(sorted(RECORDER.errors.items())),
        "skipped": dict(sorted(RECORDER.skipped.items())),
    }


def default_result_name(suite):
    name = f"{_pyproject_version()}-py{_interpreter_tag()}"
    return name if suite == "default" else f"{name}-{suite}"


def save_result(suite, *, name=None, results_dir=None, note=None):
    name = name or default_result_name(suite)
    result = build_result(suite, name=name, note=note)
    directory = (
        StdlibPath(results_dir) if results_dir else REPO_ROOT / "benchmarks" / "results"
    )
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{name}.json"
    with open(target, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(f"\nSaved {len(result['metrics'])} metrics to {target}")
    return target


def _samples_arg(value):
    count = int(value)
    if not 1 <= count <= MAX_SAMPLES:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_SAMPLES}")
    return count


def cli(argv=None):
    global _SAMPLES_OVERRIDE

    parser = argparse.ArgumentParser(
        description="Run the uripath benchmarks.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="write the run as JSON to benchmarks/results/<name>.json",
    )
    parser.add_argument(
        "--name",
        help="result name for --save, without .json "
        "(default: <version>-py<major.minor>-<os>-<arch>[-<suite>])",
    )
    parser.add_argument(
        "--results-dir",
        help="directory for --save (default: the benchmarks/results directory beside this script)",
    )
    parser.add_argument(
        "--samples",
        type=_samples_arg,
        help=f"samples per metric for every case, 1-{MAX_SAMPLES} "
        "(default: each case's own count, 1-5)",
    )
    parser.add_argument("--note", help="free-text note stored in the saved JSON")
    args = parser.parse_args(argv)
    _SAMPLES_OVERRIDE = args.samples

    main()
    if args.save:
        save_result(
            "default",
            name=args.name,
            results_dir=args.results_dir,
            note=args.note,
        )


if __name__ == "__main__":
    cli()
