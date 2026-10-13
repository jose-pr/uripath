# uripath

[![Version](https://img.shields.io/pypi/v/uripath.svg)](https://pypi.org/project/uripath/)
[![Python versions](https://img.shields.io/pypi/pyversions/uripath.svg)](https://pypi.org/project/uripath/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/jose-pr/uripath/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://jose-pr.github.io/uripath/)
[![CI](https://img.shields.io/github/actions/workflow/status/jose-pr/uripath/test.yml)](https://github.com/jose-pr/uripath/actions/workflows/test.yml)

**One `pathlib`-style API for URIs.** `UriPath("https://...")`, `UriPath("zip:...")`
and `UriPath("ftp://...")` return the class registered for the scheme, and each
has the method names, signatures and exception types of `pathlib.Path`: write
code once and run it against a local file, an archive member, an FTP or WebDAV
server, a web directory or a GitHub or GitLab repository. It builds on
[`pathlib-next`](https://github.com/jose-pr/pathlib-next) and is documented at
<https://jose-pr.github.io/uripath/>.

## Features

| Scheme (class) | Read | Write | List | Stat | mkdir | Delete | rename |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `file:` (`FileUri`) | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `data:` (`DataUri`, RFC 2397) | Yes | No | No | Yes | No | No | No |
| `zip:` (`ZipUri`) | Yes | Local `file:` archive only | Yes | Yes | Local archive only | Local archive only | Local archive only |
| `tar:` (`TarUri`, incl. gz/bz2/xz) | Yes | No | Yes | Yes | No | No | No |
| `archive:`, `archive+zip:`, `archive+tar:` | As `zip:`/`tar:` for the detected or pinned format | | | | | | |
| `ftp:` / `ftps:` (`FtpPath`) | Yes | Yes | Yes (MLSD, NLST fallback) | Yes | Yes | Yes | Yes |
| `http:` / `https:` (`HttpPath`) | Yes | Yes (PUT, configurable) | Yes (HTML index) | Yes | No | Yes (DELETE) | No |
| `dav:` / `davs:` (`DavPath`, WebDAV) | Yes | Yes (no append) | Yes (PROPFIND) | Yes | Yes | Yes | Yes |
| `github:` / `gitlab:` / `git:` | Yes | No | Yes | Yes | No | No | No |

Every scheme gets `glob()`, `walk()`, `copy()`/`move()`, `rm()` and `PathSyncer`
from the `pathlib-next` base classes. The per-scheme notes (timeouts,
certificate verification, authentication, limits) are in
[Schemes](https://jose-pr.github.io/uripath/guides/schemes/).

- **Pure URI algebra**: `Uri` parses, joins and compares URIs with no I/O and
  no scheme class needed; `Source` and `Query` are its authority and query.
- **HTTP on the standard library**: `http:`, `dav:`, `github:`, `gitlab:` and
  `git:` send through a replaceable transport built on `http.client`.
- **Extensible**: subclass `UriPath` and declare `__SCHEMES` for a new scheme,
  or register it through a `uripath.schemes` entry point.
- **Other distributions** provide what needs a third-party library: `sftp:`
  (`uripath-sftp`), `s3:`, `gs:` and `az:` (`uripath-objstore`) and the
  `requests` HTTP transport (`uripath-http-requests`). Using one of these
  schemes without its distribution raises an `ImportError` that names it.
- **`uripath` command**: `read`, `write`, `cp`, `rm` and `sync` across local
  paths and URIs, with `-` for stdin/stdout.

## Installation

```bash
pip install uripath
```

Requires `pathlib-next`, `netimps` and `uritools`, which pip installs with it.
There are no extras.

## Quick start

**Any URI**: `UriPath` returns the class registered for the scheme:

```python
from uripath import UriPath

report = UriPath("file:data/report.txt")                    # FileUri
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text("hello")
print(report.read_text())
print(UriPath("data:text/plain;base64,aGVsbG8=").read_text())  # DataUri
```

**Archive members**: `<scheme>:<archive-uri>!/<member>`, where the archive
itself is any URI (`file:`, `http:`, `ftp:`, ...):

```python
import zipfile
from uripath import UriPath

with zipfile.ZipFile("backup.zip", "w") as archive:
    archive.writestr("etc/config.ini", "[main]\n")

member = UriPath("zip:file:backup.zip!/etc/config.ini")
print(member.read_text())
print([child.name for child in member.parent.iterdir()])
```

**Remote paths** use the same API:

<!-- example: skip: reads from remote hosts -->
```python
from uripath import UriPath

for child in UriPath("https://example.com/data/").iterdir():
    print(child.name, child.stat().st_size)

print(UriPath("ftp://user@host/pub/README").read_text())
print(UriPath("github://github.com/owner/repo/README.md?ref=main").read_text())
```

**Copy and sync across schemes**, with the `pathlib-next` syncer:

```python
from pathlib_next.sync import PathSyncer
from uripath import UriPath

source = UriPath("file:site")
(source / "css").mkdir(parents=True)
(source / "index.html").write_text("<h1>hi</h1>")

PathSyncer(remove_missing=True).sync(source, UriPath("file:site-copy"))
print(sorted(p.name for p in UriPath("file:site-copy").iterdir()))
```

## Command line

`uripath` reads, writes, copies, removes and syncs local paths and URIs, with
`-` for stdin or stdout. These commands run as written in an empty directory:

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
[CLI guide](https://jose-pr.github.io/uripath/guides/cli/).

## API overview

| Module | Purpose |
| --- | --- |
| `uripath` | `Uri`, `UriPath`, `UriLike`, `DerivedBackend`, `same_authority` |
| `uripath.source` | `Source` (scheme, userinfo, host, port) and its helpers |
| `uripath.query` | `Query` |
| `uripath.schemes` | The built-in schemes: `file`, `data`, `archive` (`zip`, `tar`), `ftp`, `http`, `dav`, `github`, `gitlab`, `git` |

The full reference is on the [documentation site](https://jose-pr.github.io/uripath/);
an agent-oriented API summary ships inside the package as `uripath/AGENTS.md`.

## Extending

Subclass `UriPath` and declare `__SCHEMES` for a new URI scheme; it is
dispatched as soon as its module is imported, or through a `uripath.schemes`
entry point. A scheme name belongs to one class: a second claim raises unless
the class statement says `replace=True`, and `UriPath.schemes()` /
`UriPath.scheme_class(name)` read the registry. Worked examples:
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
[`CHANGELOG.md`](CHANGELOG.md). Pushing a tag matching `v*` triggers the release
workflow: test gate → build (checking the tag names the version built) → a strict
docs build as a gate → GitHub release → publish. The release workflow never deploys
the docs site itself: for a final release its last job dispatches the docs workflow
at the tag, which owns every Pages deploy.

## License

MIT — see [LICENSE](LICENSE).
