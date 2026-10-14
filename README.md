# uripath

[![Version](https://img.shields.io/pypi/v/uripath.svg)](https://pypi.org/project/uripath/)
[![Python versions](https://img.shields.io/pypi/pyversions/uripath.svg)](https://pypi.org/project/uripath/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/jose-pr/uripath/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://jose-pr.github.io/uripath/)
[![CI](https://img.shields.io/github/actions/workflow/status/jose-pr/uripath/test.yml)](https://github.com/jose-pr/uripath/actions/workflows/test.yml)

**One `pathlib`-style API for URIs.** `URIPath("https://...")`, `URIPath("zip:...")`
and `URIPath("ftp://...")` return the class registered for the scheme, and each
has the method names, signatures and exception types of `pathlib.Path`: write
code once and run it against a local file, an archive member, an FTP or WebDAV
server, a web directory or, through the `repopath` distribution, a GitHub or GitLab
repository. It builds on
[`pathlib-next`](https://github.com/jose-pr/pathlib-next) and is documented at
<https://jose-pr.github.io/uripath/>.

## Features

| Scheme (class) | Needs | Read | Write | List | Stat | mkdir | Delete | rename |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `file:` (`FileURIPath`) | nothing | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `data:` (`DataURIPath`, RFC 2397) | nothing | Yes | No | No | Yes | No | No | No |
| `zip:` (`ZipURIPath`) | nothing | Yes | Local `file:` archive only | Yes | Yes | Local archive only | Local archive only | Local archive only |
| `tar:` (`TarURIPath`, incl. gz/bz2/xz) | nothing | Yes | No | Yes | Yes | No | No | No |
| `archive:`, `archive+zip:`, `archive+tar:` | nothing | As `zip:`/`tar:` for the detected or pinned format | | | | | | |
| `ftp:` / `ftps:` (`FTPURIPath`) | nothing | Yes | Yes | Yes (MLSD, NLST fallback) | Yes | Yes | Yes | Yes |
| `http:` / `https:` (`HTTPURIPath`) | nothing | Yes | Yes (PUT, configurable) | Yes (HTML index) | Yes | No | Yes (DELETE) | No |
| `dav:` / `davs:` (`DAVURIPath`, WebDAV) | nothing | Yes | Yes (no append) | Yes (PROPFIND) | Yes | Yes | Yes | Yes |
| `sftp:` | `sftppath[paramiko]` or `[asyncssh]` | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `s3:` | `objpath[s3]` | Yes | Yes (no append) | Yes (prefixes) | Yes | Yes (marker object) | Yes | Yes (same bucket) |
| `gs:` | `objpath[gs]` | Yes | Yes (no append) | Yes (prefixes) | Yes | Yes (marker object) | Yes | Yes (same bucket) |
| `az:` | `objpath[az]` | Yes | Yes (no append) | Yes (prefixes) | Yes | Yes (marker blob) | Yes | Yes (same container) |
| `repo:` | `repopath` | Yes | No | Yes | Yes | No | No | No |
| `github:` | `repopath` | Yes | No | Yes | Yes | No | No | No |
| `gitlab:` | `repopath` | Yes | No | Yes | Yes | No | No | No |

The last seven rows are other distributions: a path of one of those schemes
builds, joins and prints without it, and its first use of the server raises an
`ImportError` that names what to install. The `requests` HTTP transport
(`with_session()`, `~/.netrc`, SOCKS proxies) is the distribution
`pathlib-next-requests`: once it is installed, `with_session()` and
`PATHLIB_NEXT_HTTP_TRANSPORT=requests` use it, with nothing to configure.

Every scheme gets `glob()`, `walk()`, `copy()`/`move()`, `rm()` and `PathSyncer`
from the `pathlib-next` base classes. The per-scheme notes (timeouts,
certificate verification, authentication, limits) are in
[Schemes](https://jose-pr.github.io/uripath/guides/schemes/).

- **Pure URI algebra**: `URI` parses, joins and compares URIs with no I/O and
  no scheme class needed; `Source` and `Query` are its authority and query.
- **HTTP on the standard library**: `http:` and `dav:` send through a
  replaceable transport built on `http.client`.
- **Extensible**: subclass `URIPath` and declare `__SCHEMES` for a new scheme,
  or register it through a `uripath.schemes` entry point.
- **`uripath` command**: `read`, `write`, `cp`, `rm` and `sync` across local
  paths and URIs, with `-` for stdin/stdout (`pip install "uripath[cli]"`).

## Installation

```bash
pip install uripath
```

Requires `pathlib-next` and `netimps`, which pip installs with it.

| Install | Adds |
| --- | --- |
| `pip install uripath` | every scheme whose Needs is nothing in the table above |
| `pip install "uripath[cli]"` | the `uripath` command (its only extra) |
| `pip install "sftppath[paramiko]"` or `[asyncssh]` | `sftp:` |
| `pip install "objpath[s3]"`, `[gs]` or `[az]` | `s3:`, `gs:`, `az:` |
| `pip install pathlib-next-requests` | the `requests` HTTP transport |

## Quick start

**Any URI**: `URIPath` returns the class registered for the scheme:

```python
from uripath import URIPath

report = URIPath("file:data/report.txt")                    # FileURIPath
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text("hello")
print(report.read_text())
print(URIPath("data:text/plain;base64,aGVsbG8=").read_text())  # DataURIPath
```

**Archive members**: `<scheme>:<archive-uri>!/<member>`, where the archive
itself is any URI (`file:`, `http:`, `ftp:`, ...):

```python
import zipfile
from uripath import URIPath

with zipfile.ZipFile("backup.zip", "w") as archive:
    archive.writestr("etc/config.ini", "[main]\n")

member = URIPath("zip:file:backup.zip!/etc/config.ini")
print(member.read_text())
print([child.name for child in member.parent.iterdir()])
```

**Remote paths** use the same API:

<!-- example: skip: reads from remote hosts -->
```python
from uripath import URIPath

for child in URIPath("https://example.com/data/").iterdir():
    print(child.name, child.stat().st_size)

print(URIPath("ftp://user@host/pub/README").read_text())
```

**Copy and sync across schemes**, with the `pathlib-next` syncer:

```python
from pathlib_next.sync import PathSyncer
from uripath import URIPath

source = URIPath("file:site")
(source / "css").mkdir(parents=True)
(source / "index.html").write_text("<h1>hi</h1>")

PathSyncer(remove_missing=True).sync(source, URIPath("file:site-copy"))
print(sorted(p.name for p in URIPath("file:site-copy").iterdir()))
```

## Command line

`uripath` reads, writes, copies, removes and syncs local paths and URIs, with
`-` for stdin or stdout. It is built on `duho` and needs the `cli` extra,
`pip install "uripath[cli]"`; without it the command says so and exits with
status 1. These commands run as written in an empty directory:

```bash
mkdir site
uripath write site/index.html "<h1>hi</h1>"
uripath read site/index.html
uripath cp site/index.html site/copy.html
uripath sync --dry-run --remove-missing site site-copy
uripath sync site site-copy
uripath rm --recursive site-copy
```

Either side can be a URI instead:

<!-- example: skip: needs an FTP host and a web server -->
```bash
uripath cp report.txt ftp://host/tmp/report.txt
uripath sync --dry-run --remove-missing site/ ftp://host/site/
```

The exit status is 0 on success, 1 when the operation failed, 2 for a wrong
invocation, 130 on Ctrl-C and 141 when the reader of stdout went away. Every
flag is described in the
[CLI guide](https://jose-pr.github.io/uripath/guides/cli/), and `uripath` can
be served to an agent as a set of tools.

## API overview

| Module | Purpose |
| --- | --- |
| `uripath` | `URI`, `URIPath`, `URILike`, `Source`, `Query`, `QueryLike`, the functions `as_path` and `copy_stream`, the errors `URIPathError`, `URISyntaxError` and `UnsupportedSchemeError`, and `__version__` |
| `uripath.source` | `Source` (scheme, userinfo, host, port), `same_authority` and the helpers that read and compose a URI's text |
| `uripath.query` | `Query`, an immutable query value, and `QueryLike` |
| `uripath.exceptions` | The errors above |
| `uripath.schemes` | The contract and registry of schemes, `DerivedBackend`, `DelegatingURIPath`, and every built-in scheme's classes: `FileURIPath`, `DataURIPath`, `ZipURIPath`, `TarURIPath`, `ArchiveURIPath`, `FTPURIPath`, `HTTPURIPath`, `DAVURIPath` and their backends |

The full reference is on the [documentation site](https://jose-pr.github.io/uripath/);
an agent-oriented API summary ships inside the package as `uripath/AGENTS.md`.

## Extending

Subclass `URIPath` and declare `__SCHEMES` for a new URI scheme; it is
dispatched as soon as its module is imported, or through a `uripath.schemes`
entry point. A scheme name belongs to one class: a second claim raises unless
the class statement says `replace=True`, and `URIPath.schemes()` /
`URIPath.scheme_class(name)` read the registry. Worked examples:
[Extending](https://jose-pr.github.io/uripath/guides/extending/). The pytest
contracts that verify a scheme are in `pathlib_next.testing`.

## Development

```bash
pip install -e ".[dev]"
python -m pytest -q -rs
```

Tests for a server that is not installed are skipped, so check the skip list
(`-rs`). Contributor notes (virtual environments, formatting, CI, releases) are
in the repository's
[`AGENTS.md`](https://github.com/jose-pr/uripath/blob/main/AGENTS.md). To
preview the documentation: `pip install -e ".[docs]"` then `mkdocs serve`.

Changes are recorded in the
[changelog](https://github.com/jose-pr/uripath/blob/main/CHANGELOG.md).

### Releasing

This project follows [Semantic Versioning](https://semver.org/) and keeps a
[`CHANGELOG.md`](https://github.com/jose-pr/uripath/blob/main/CHANGELOG.md). Pushing a tag matching `v*` triggers the release
workflow: test gate → build (checking the tag names the version built) → a strict
docs build as a gate → GitHub release → publish. The release workflow never deploys
the docs site itself: for a final release its last job dispatches the docs workflow
at the tag, which owns every Pages deploy.

## License

MIT — see [LICENSE](https://github.com/jose-pr/uripath/blob/main/LICENSE).
