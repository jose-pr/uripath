# Extending

A new URI scheme is a `URIPath` subclass. You implement a small method surface;
everything else (`open`/`read_text`/`write_text`/`glob`/`walk`/`touch`/`rm`/
`copy`/`move`/`exists`/`is_dir`/`is_file`/...) is *derived* from the protocols
in `pathlib_next.protocols`. The class registers itself and gets URI parsing,
joining, query and fragment handling from `URI`.

A resource that is not naturally a URI (a database-backed virtual filesystem, a
key-value store) is a subclass of `pathlib_next.Path` instead; that is
described in the
[pathlib-next guide](https://jose-pr.github.io/pathlib-next/guides/extending/).

Run the shared contract suite against your implementation -- see
[Testing your implementation](#testing-your-implementation) below.

## Subclass `URIPath`

The pure-path side (parsing, join, query/fragment, `with_*`) comes from `URI`.
Register the scheme and implement the I/O surface:

```python
import errno
import os

from uripath import URIPath
from pathlib_next import FileStat


class MyPath(URIPath):
    __SCHEMES = ("myscheme",)  # name-mangled: declare it in every class

    def _initbackend(self):
        # Connection or session state, created on first use and shared by
        # every path derived from this one on the same endpoint.
        return None

    def _scandir(self):
        # Or implement `_listdir()` to yield names only.
        yield from ()

    def stat(self, *, follow_symlinks=True):
        hint = self._pop_stat_hint()  # metadata from the parent's listing
        if hint is not None:
            return hint
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(self))

    def _open(self, mode="r", buffering=-1):
        raise NotImplementedError(f"open(mode={mode!r})")

    def rename(self, target):
        target = self._rename_target(target)  # sibling str, same endpoint only
        ...  # rename self.path to target.path on the server
        return self.with_path(target.path)


print(type(URIPath("myscheme://host/data/file.txt")).__name__)
```

Defining (importing) the subclass is enough: `URIPath("myscheme://...")`
dispatches to it, also when the class is defined after the first dispatch.
The class name must not start with an underscore, or the name-mangled
`__SCHEMES` lookup misses it, and a subclass that lists no `__SCHEMES` of its
own registers nothing, whatever it inherits.

A distribution that ships schemes declares each one as an entry point, so
that installing it is enough and nothing has to import its module first:

```toml
[project.entry-points."uripath.schemes"]
myscheme = "mypackage.paths:MyPath"
```

The entry point only loads the module; defining the class is what registers
the names it lists, so there is no separate registration call.

### Names are held by one class

A scheme name belongs to one class. Defining a second class that lists a name
another class holds raises `ValueError` at the `class` statement, naming the
holder, and the class registers none of its names. The built-in names (`file`,
`http`, `ftp`, ...) are held by the built-in classes even before their
modules are imported, and a distribution's entry point never takes one: the
built-in module is consulted before the entry points. The names of the
schemes that other distributions provide (`sftp`, `s3`, `gs`, `az`) are open: a
distribution that registers one through this entry-point group takes it. To replace a class on
purpose, say so in the class statement:

```python
from uripath import URIPath


class MyHttp(URIPath, replace=True):
    __SCHEMES = ("http", "https")


assert URIPath.scheme_class("https") is MyHttp
assert type(URIPath("http://example.com/x")) is MyHttp
```

A built-in class defined after a replacement leaves it in place. Paths built
before the replacement keep their class. Running the same class statement
again (same module and qualified name: `importlib.reload()`, a function called
twice, a notebook cell) is not a second claim: the newer class takes the name
without `replace=True`. A class of another module, or of another qualified
name, is still refused.

`URIPath.schemes()` lists the registered names, sorted, including built-in
and entry-point schemes whose module is not imported yet and the schemes
that other distributions provide (those fail where they are used, naming the
distribution to install). `URIPath.scheme_class(name)` returns the class registered for a
name, importing or loading it first, or raises `UnsupportedSchemeError` naming the
registered schemes:

```python
from uripath import URIPath

print(URIPath.scheme_class("data").__name__)  # DataURIPath
print("ftp" in URIPath.schemes())  # True, though its module is not imported
```

Conventions for a scheme implementation:

- Use `self.path` (percent-decoded) on the wire and `self.source`
  (`scheme`, `userinfo`, `host`, `port`, `parsed_userinfo()`) for the
  connection. `str(self)` is already redacted for error messages.
- `iterdir()` is derived from `_scandir()`, which defaults to `_listdir()`
  plus one `stat()` per child. Override `_scandir()` when one listing call
  returns type, size and mtime (an HTML index, `PROPFIND`, `MLSD`): each child's first `stat()` then returns the
  listing's metadata through `_pop_stat_hint()`, and later calls fetch
  again, so a remote walk costs one request per directory.
- `rename()` and `symlink_to()` receive a `str` as a decoded path, not URI
  syntax; `_rename_target()` resolves a relative one against the parent and
  raises `NotImplementedError` for another endpoint, which makes `move()`
  copy instead. Override `_same_location()` when your namespace is narrower
  than the authority (an archive, a container).
- A derived path (`/`, `parent`, `with_name()`, `relative_to()`, ...) never
  calls `_initbackend()`: it takes the backend its source already holds, and
  only for the same scheme, userinfo, host and port. Paths derived from one
  another share one slot for the backend they derive for themselves, which
  the first of them to need one fills with `_initbackend()` (under a lock);
  a path constructed on its own builds its own on first use.
- Set `_host_filesystem_path = True` only when `self.path` is a real
  filesystem path on the remote host; `os.fspath()` and
  `host_fspath()` then return it.
- Build a child by name with `_make_child_relpath(name)` (it keeps the query
  and the fragment of its parent, like every derivation that changes only the
  path) and a path from decoded components with
  `_from_parsed_parts(source, path, query, fragment)`; neither parses its
  argument. A constructor-level override goes in
  `_init(source, path, query, fragment, **kwargs)`, which every construction
  ends in, and calls `super()._init()`. Two paths are on one endpoint when
  `uripath.source.same_authority(a.source, b.source)`; a host keeps the spelling
  it was given, so key anything kept per server on
  `uripath.source.fold_host(source.host)`.
- A scheme whose constructor reads keyword arguments of its own names them in
  `_OPTIONS` (`_OPTIONS = URIPath._OPTIONS | {"flavor"}`): any other keyword is a
  `TypeError`.
- A backend that cannot be written piecewise (an FTP `STOR`, an archive
  rewrite) is returned from `_open()` as
  `pathlib_next.providers.CommitOnClose(commit)`: `commit(buffer)` runs once,
  when the stream is closed. A stream of your own that commits on close
  inherits `pathlib_next.providers.DiscardOnError`, first in its bases, and
  defines `discard()`, so that a `with` block that raised commits nothing.

The shipped API header (`AGENTS.md` inside the package) lists the hooks and
helpers of `URIPath` with their signatures, under "For scheme implementers";
the one inside `pathlib_next` lists those of `Path`, under "For path
implementers". The built-in schemes use no other underscore name of either.

### Delegate to a path that needs no URI

A protocol that is useful without a URI (a path to an FTP server, to an SFTP
server) is best written once, as a `pathlib_next.Path` that takes its endpoint
as keywords, and offered as a scheme by a thin class on top of it. Subclass
`uripath.schemes.DelegatingURIPath`, list the hooks to hand over in
`_DELEGATED` and build the path they run on in `_make_core()`:

```python
from pathlib_next import MemPath
from uripath.schemes import DelegatingURIPath


class MemURIPath(DelegatingURIPath):
    __SCHEMES = ("mem",)
    _DELEGATED = ("_scandir", "_listdir", "_open", "_mkdir", "unlink", "rmdir")

    def _make_core(self):
        return MemPath(self.path or "/", backend=SHARED_BACKEND)
```

Everything about URIs (parsing, joining, how paths of one endpoint share a
backend, the keywords of the constructor) stays in the URI class; the protocol,
its errors and its connections stay in the core path, and an `OSError` the core
path raises names the URI path instead of its own. A hook the scheme must
change before it delegates (`rename()`, `copy()`) is written by hand and runs
the core path inside `with self._delegated():`.

The built-in schemes are worked examples of increasing size:
[`FileURIPath`](../api/schemes/local.md) delegates to `LocalPath`,
[`FTPURIPath`](../api/schemes/ftp.md) adapts the `pathlib_next` FTP path to a
URI, and [`HTTPURIPath`](../api/schemes/http.md) scrapes HTML listings behind a
replaceable transport.

## Provide an HTTP transport

`http:`, `dav:`, `github:` and `gitlab:` send through a transport that
`pathlib_next.http` defines: any object with `send(method, url, *, headers,
body=None, timeout, stream=False)` and `close()`. A distribution provides one by
declaring a class that is built with no arguments in the entry-point group
`pathlib_next.http_transports`, so that installing it is enough; how, what
`prepare_request()` checks for you and the suite that holds the transport to the
same promises (`python -m pathlib_next.http.testing --http-transports NAME`) are
in the `pathlib-next` documentation. `PATHLIB_NEXT_HTTP_TRANSPORT=mytransport`
then makes every backend that was given no transport build `MyTransport()`, and
`path.with_transport(MyTransport(...))` installs one by hand. The name `requests`
is the one `path.with_session()` and `RepoBackend(session=...)` build, with the
session as the first argument; the distribution `pathlib-next-requests` provides
it.

## Testing your implementation

To ensure custom implementations comply with `pathlib_next`'s expected behaviors, the library offers three contract levels in `pathlib_next.testing` which can be mixed into your `pytest` suite:

1. **`PurePathContract`**: Covers logical pure-path operations (joining, parents, stems, suffix checks, and glob matching) that do not require any physical I/O.
2. **`ReadPathContract`**: Extends `PurePathContract` to verify read-only I/O: `exists()`/`is_file()`/`is_dir()`, `read_text()`/`read_bytes()`, `open()` read modes, `iterdir()`, `stat()`, `glob()`/`rglob()` and `walk()`, plus the error paths with pathlib's exception types (a missing path raises `FileNotFoundError`, listing a file `NotADirectoryError`, reading a directory `IsADirectoryError` or, as pathlib does on Windows, `PermissionError`).
3. **`PathContract`**: Extends `ReadPathContract` to verify writes: `mkdir()`, `write_text()`/`write_bytes()`, `open()` write/append/exclusive modes, `unlink()`, `rmdir()`, `rm()` (also called with `follow_symlinks=` and `follow_binds=`), `copy()` (including `recursive=True`), `move()`, `rename()` and `touch()`, again with their error paths (a missing parent raises `FileNotFoundError`, `rmdir()` of a file `NotADirectoryError`, of a non-empty directory `OSError(ENOTEMPTY)`).

Both I/O levels need a `root` fixture pointing at a **fresh, function-scoped** directory holding the standard tree (`a.txt`, `b.py`, `.hidden.txt`, `sub/c.py`, `sub/nested/d.py`, `empty_dir/`). `populate_fixture_tree(root)` builds it through your path's own `mkdir()`/`write_text()`. The write tests create fixed names under `root` without cleaning up, so two contract classes must never share one.

### Example: Running the full contract

<!-- example: skip: a pytest module, not a program -->
```python
import pytest

from pathlib_next import LocalPath as MyPath  # your Path subclass here
from pathlib_next.testing import PathContract, populate_fixture_tree


class TestMyPath(PathContract):
    @pytest.fixture
    def root(self, tmp_path):
        root = MyPath(tmp_path)
        populate_fixture_tree(root)
        return root
```

### Capability attributes

A backend that genuinely cannot meet a rule sets the matching class attribute to `False` on its test class. The affected tests then report as skipped, never as passed. Every attribute defaults to `True` except `supports_question_mark_names`; set one only for a documented gap.

| Attribute | Contract | Covers | Built-in schemes that set it `False` |
| --- | --- | --- | --- |
| `supports_listing` | `ReadPathContract` | `iterdir()`, `glob()`, `walk()` | `DataURIPath` (a single resource) |
| `supports_empty_directories` | `ReadPathContract` | `empty_dir/` lists as empty | `GitHubURIPath`, `GitLabURIPath` (git trees cannot hold an empty directory) |
| `distinguishes_file_types` | `ReadPathContract` | listing a file raises `NotADirectoryError`; reading a directory raises | `HTTPURIPath` (one URL serves an index page or a file) |
| `supports_pickle` | `ReadPathContract` | `pickle.loads(pickle.dumps(path))` is equal to the path and hashes alike | none |
| `supports_rename` | `PathContract` | `rename()` | none here (`MemPath` of `pathlib_next` sets it: `move()` copies instead) |
| `supports_append` | `PathContract` | `open("a")` | `ZipURIPath`, `DAVURIPath` |
| `supports_exclusive_create` | `PathContract` | `open("x")` | none |
| `enforces_directory_hierarchy` | `PathContract` | `mkdir()`/writes below a missing parent raise `FileNotFoundError`; writing a file over a directory raises; `rename()` onto a non-empty directory raises | none (the object stores of `objpath` set it) |
| `supports_mkdir` | `PathContract` | `mkdir()`, and every test that creates a directory | none (a transport with no directories, such as TFTP, sets it) |
| `supports_delete` | `PathContract` | `unlink()`, `rmdir()`, `rm()`, and replacing a file in `copy(overwrite=True)` | none (TFTP sets it) |
| `supports_move` | `PathContract` | `move()`, by `rename()` or by copying and deleting | none (TFTP sets it) |
| `supports_unusual_names` | `PathContract` | names holding a space, `#`, `%`, `+`, `&`, `=` and mixed case are stored and listed as written | none |
| `supports_utime` | `PathContract` | `_utime()` sets an existing file's modification time and `touch()` of it moves the time | `ZipURIPath`, `archive:`/`archive+zip:`, `DAVURIPath` (no settable time) |
| `supports_question_mark_names` | `PathContract` | the same for names holding `?`. **Defaults to `False`**: a Windows file system cannot store such a name | `True` for `ZipURIPath`, and where the machine can store one for `FileURIPath`, `FTPURIPath`, `DAVURIPath` |

### Which contract runs against the built-in schemes?

`tests/test_contract.py` runs:

- **Full `PathContract`**: `LocalPath`, `MemPath`, `FileURIPath`, `ZipURIPath` and `archive:`/`archive+zip:` (local outer archive), `FTPURIPath` (in-process pyftpdlib) and `DAVURIPath` (in-process WsgiDAV).
- **`ReadPathContract`**: `HTTPURIPath` (local HTTP server), `TarURIPath` and `archive:`/`archive+tar:`, `DataURIPath` (listing skipped), and `GitHubURIPath`/`GitLabURIPath` and their `git+github:`/`git+gitlab:` spellings (in-process fake APIs).

See `tests/test_contract.py` for how each scheme's `root` fixture is wired.
