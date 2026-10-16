# uripath

**One `pathlib`-style API for URIs.** `URIPath("https://...")`, `URIPath("zip:...")`
and `URIPath("ftp://...")` return the class registered for the scheme, and each
has the method names, signatures and exception types of `pathlib.Path`: write
code once and it works against a local file, an archive member, an FTP or
WebDAV server or a web directory, and any scheme another distribution registers.
`uripath`
builds on [`pathapi`](https://jose-pr.github.io/pathapi/), which holds
the `Path` base classes, the local, in-memory, FTP and archive paths, `glob` and
`PathSyncer`.

Deliberate behavioral differences from `pathlib` are listed, with their
reasons, in [Divergences from pathlib](divergences.md).

## Installation

```bash
pip install pathapi-uri
```

It requires `pathapi` and `netimps`, which pip installs with it; its one
extra, `cli`, adds the `uripath` command
(`pip install "pathapi-uri[cli]"`). The schemes of this package run on the standard
library, including HTTP. Another scheme is a class that a distribution registers
in the `uripath.schemes` entry-point group (see "Other schemes" in
[Schemes](guides/schemes.md)).

## Tour

**URIs**: `URIPath` returns the class registered for the scheme:

```python
from uripath import URIPath

report = URIPath("file:data/report.txt")
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text("hello")
print(type(report).__name__, report.read_text())

inline = URIPath("data:text/plain;base64,aGVsbG8=")
print(type(inline).__name__, inline.read_text())
```

**Archives**: a member inside a zip or tar, the archive itself addressed by any
URI:

```python
import zipfile
from uripath import URIPath

with zipfile.ZipFile("backup.zip", "w") as archive:
    archive.writestr("etc/config.ini", "[main]\n")

member = URIPath("zip:file:backup.zip!/etc/config.ini")
print(member.read_text())
```

**Remote schemes** share the same contract (these need a reachable server):

<!-- example: skip: reads from remote hosts -->
```python
from uripath import URIPath

for child in URIPath("https://example.com/data/").iterdir():
    print(child.name, child.stat().st_size)

print(URIPath("ftp://user@host/pub/README").read_text())
```

`exists()`, `is_dir()`, `iterdir()`, `glob()`, `walk()`,
`read_text()`/`write_text()`, `copy()`/`move()` and `rm()` behave the same way
on every backend; what a backend cannot do (for example `mkdir()` over plain
HTTP, or any write to a `data:` path) raises `NotImplementedError`. The
per-scheme capabilities are in [Schemes](guides/schemes.md).

## Where to go next

- **[Schemes](guides/schemes.md)**: capability matrix and per-scheme notes
  (timeouts, authentication, security defaults).
- **[CLI](guides/cli.md)**: the `uripath` command.
- **[Extending](guides/extending.md)**: add a scheme by subclassing `URIPath`,
  and verify it with the bundled contracts.
- **[Divergences from pathlib](divergences.md)**: every deliberate behavioral
  difference from `pathlib.Path`.
- **[API Reference](api/uri.md)**: generated from the docstrings.
- **[Changelog](changelog.md)**.
