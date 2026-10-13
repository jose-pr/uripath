# `uripath` — public API header

Header-file-style reference for the `uripath` package: every public export
with its signature, arguments, contract and gotchas, so the package can be used
without reading its source. It ships inside the package and is self-contained.
Development documentation lives with the source at
<https://github.com/jose-pr/uripath>; the rendered documentation is at
<https://jose-pr.github.io/uripath/> and the project overview is the
`README.md` shipped next to this file (`uripath/README.md`). The classes are
`pathlib`-shaped, built on `pathlib_next.Path` and `pathlib_next.Pathname`
(the `pathlib-next` distribution): their method names, signatures and
exception types are those of `pathlib.Path`, and every deliberate difference is
listed, with its rationale, at <https://jose-pr.github.io/uripath/divergences/>.

Names are imported from the module named in the heading of the section that
documents them; the root `uripath` exports `Uri`, `UriPath` and `UriLike`. A
module or name that starts with an underscore is private: where this file names
one (`uripath.schemes._gitrepo`, `uripath.schemes.archive._base`) it names the
public names to use from it, and nothing else there is contract. The schemes
need no client library: they run on the standard library and on `pathlib_next`.
`sftp:`, `s3:`, `gs:` and `az:` and the `requests` HTTP transport are provided by
other distributions ("Provided by other distributions").

`pip install uripath`. Required dependencies: `pathlib-next>=0.10.0,<0.11`,
`netimps>=0.4.0,<0.5` and `uritools>=5.0,<7`. There are no extras.

## URIs (`uripath`)

The URI layer builds on `Path` and `Pathname` of `pathlib_next`: the method
surface of `Path` (`read_text()`, `iterdir()`, `glob()`, `walk()`, `copy()`,
`move()`, `rm()`, ...) is that of the `pathlib-next` header.

### `Uri`

```python
class Uri(Pathname):
    def __init__(self, *uris, **options): ...
    source: Source
    path: str
    query: str
    fragment: str
    stem
    suffix
    parts
    normalized_path
    segments
    parent
    def as_uri(self, sanitize=False): ...
    def with_source(self, source): ...
    def with_path(self, path): ...
    def with_segments(self, *segments): ...
    def with_query(self, query): ...
    def with_fragment(self, fragment): ...
    def with_name(self, name) -> Self: ...
    def with_suffix(self, suffix) -> Self: ...
    def with_stem(self, stem) -> Self: ...
    def is_absolute(self): ...
    def is_relative_to(self, other): ...
    def relative_to(self, other, *, walk_up=False): ...
    def is_local(self): ...
    def as_posix(self): ...
    def __fspath__(self): ...
    def host_fspath(self) -> str: ...
```

Pure RFC 3986 URI, parsed lazily. Arguments
(`str`, `bytes`, `Uri`, `pathlib`/`pathlib_next` paths, `os.PathLike`;
`None` and `""` are the empty URI, anything else is a `TypeError` naming its
type) join right to left like `joinpath` (an absolute one restarts); this is not RFC
3986 reference resolution (`Uri("http://h/d") / "x"` is `http://h/d/x`),
but the dot segments of the joined path are removed as RFC 3986 5.2.4
says: `Uri("http://h/d/", "../x")`, `Uri("http://h/d/") / "../x"`,
`Uri("http://h/d/") / Uri("../x")` and `Uri("http://h/d/../x")` are all
`http://h/x`, and `Uri("http://h/d/x") / ".."` is `http://h/d/`. A `..`
that would pass the root of an absolute path is dropped; a relative path
keeps its leading `..` (`Uri("a") / "../../x"` is `../x`). A
percent-encoded dot segment (`%2e%2e`) is removed after decoding. An
absolute local path **object** (`pathlib.Path`, `LocalPath`) becomes
`file:`; a relative one joins like a `PurePath`. A `str` argument is always
URI text: wrap a path string (`LocalPath(s)`), because `UriPath("/abs/x")`
is a path with no scheme whose I/O raises `NotImplementedError` and
`UriPath("C:/Temp/x")` has the scheme `c`.

- Properties: `source -> Source`, `path -> str` (percent-decoded),
  `query -> Query` (**percent-encoded as received**, sent unchanged; empty
  when there is none), `fragment -> str` (`""` when there is none),
  `parts -> (source, path, query, fragment)` (not path
  segments; use `segments`), `normalized_path`, `segments`, `parent`
  (`http://h/a` → `http://h/`; a trailing `/` is kept, so
  `Uri("http://h/d/").name == ""`).
- Methods: `as_uri(sanitize=False)`, `with_source()`, `with_path()`,
  `with_segments()`, `with_query(str | mapping | pairs)` (a `str` is taken as
  already encoded), `with_fragment()`; `with_name`/`with_suffix`/`with_stem`
  keep query and fragment. `with_path(path)` gives a relative path under an
  authority the leading `/` the constructor gives it; `with_segments(*segments)`
  joins the spelling `segments` returns (a leading `""` is the root) with `/`,
  and an element may be `str`, `bytes`, a `PurePath` or an `os.PathLike`.
  `is_absolute()` (path starts with `/`),
  `is_relative_to(other)`, `relative_to(other, *, walk_up=False)`
  (`http://h` counts as the root), `is_local()`
  (`Source.is_local()`), `as_posix()` (`user@host:path` when a host is
  present).
- `stem` and `suffix` are those of `name` (the last segment of the decoded
  path; the query and the fragment are not part of it). `UriLike` =
  `str | Uri | os.PathLike`, what the constructor and the join accept.
- `str()`/`repr()` drop the password (`ftp://u:pw@h/p` → `ftp://u@h/p`);
  `as_uri(sanitize=False)` keeps it. Non-ASCII hosts render as IDNA. A
  query or fragment is printed as it is: a token carried there shows in
  `str()`/`repr()`.
- Authority: the first unescaped `:` of the userinfo separates user from
  password (`us%3Aer:pw` is the user `us:er`); a host of digits only
  (`http://20240101/key`) is the host; a port is 0-65535 (`ValueError`
  otherwise, as for a `:` followed by anything but digits); an IPv6 zone is
  written `[fe80::1%25eth0]` (a bare `%` is read too). A name that holds a
  lone surrogate (a Windows file name can) renders as its UTF-8 bytes, so
  `str()`, `hash()` and `==` work on it.
- `==`/`hash` use the URI text; equal to another `Uri` or a URI string,
  never to a non-URI `Pathname`.
- `__fspath__()` — the path for a `file:` URI on this machine (a named host
  on Windows is a UNC path) or for a scheme with `_host_filesystem_path =
  True` (a scheme whose path is meaningful on **its** host); otherwise
  `NotImplementedError`. `host_fspath()` — the latter only, never local.

### `UriPath`

```python
class UriPath(Uri, Path):
    def __init__(
        self, *args, schemesmap=None, findclass=False, **kwargs,
    ): ...
    @classmethod
    def __init_subclass__(cls, replace=False, **kwargs): ...
    @classmethod
    def schemes(cls) -> tuple[str, ...]: ...
    @classmethod
    def scheme_class(cls, name) -> type[UriPath]: ...
    backend
    def with_backend(self, backend): ...
    def _initbackend(self): ...
    def _listdir(self) -> Iterator[str]: ...
    def _scandir(self) -> Iterator[Tuple[str, Optional[FileStat]]]: ...
    def _reduce_options(self) -> dict: ...
```

`Uri` + `Path`. The bare class (or `findclass=True`)
returns the subclass registered for the scheme, or plain `UriPath` for an
unknown scheme (its I/O raises `NotImplementedError`). Keywords other than
`schemesmap` and `findclass` are options of the path: `backend=` (see `backend`
below) and those the scheme class reads. Resolution: classes
already imported → built-in `uripath.schemes.*` module → entry point
in group `uripath.schemes`, and an entry point never takes a built-in
name. An explicit `schemesmap` is the only map consulted. It is an allow-list of classes for dispatch, not a sandbox:
the path keeps it and every class chosen after construction uses it -- a
join with a `Uri`/`UriPath` argument, `with_source()`, a `copy()`/`move()`
`str` destination and the outer URI of a `zip:`/`tar:`/`archive:` path (a
scheme the map omits gives a plain `UriPath`, whose I/O raises
`NotImplementedError`) -- but it restricts nothing an already-built path or
class does.

- Registering: `__SCHEMES = ("myscheme",)` in the class body (name-mangled:
  redeclare per class, a subclass that lists none registers none; the class
  name must not start with `_`). Defining or importing the subclass is
  enough, including after the first dispatch, and it is the one mechanism: a
  distribution that ships schemes declares them as entry points of the
  group `uripath.schemes` (`myscheme = "pkg.module:MyPath"`) and the
  class registers itself when the entry point is loaded. A name another
  class holds, or a built-in name (whether or not its module is imported
  yet), raises `ValueError` at the class statement, naming the holder and
  registering none of the class's names; `class MyPath(UriPath,
  replace=True)` takes the names it lists from whatever held them. The same
  class statement run again (same `__module__` and `__qualname__`, as
  `importlib.reload()` or a function called twice does) is the same class:
  the newer one takes its names without `replace=True`. A built-in class
  defined after a replacement leaves the replacement in place.
- `schemes() -> tuple[str, ...]` — the registered names, sorted: every
  class defined so far, every built-in scheme and every entry point of the
  group, whether or not its module is imported yet, and the schemes another
  distribution provides (`sftp`, `s3`, `gs`, `az`).
  `scheme_class(name)` — the class for `name` (case-insensitive), importing
  its module or loading its entry point first; `ValueError` naming the
  registered schemes when there is none, and the `ImportError` of a
  built-in module that cannot be imported. Both are classmethods of the
  one registry, whichever class they are called on.
- `backend` — per-instance connection state from `_initbackend()` (base:
  `None`), built on first use. A derived path (`/`, `joinpath()`,
  `parent`, `parents`, `with_name()`, `with_suffix()`, `with_query()`,
  `relative_to()`, `UriPath(base, x)`, a `Uri`/`PurePath` join) never
  builds one -- so it never imports an I/O library either -- and takes the
  backend its source path already holds, or none. Paths derived from one
  another on one endpoint share one slot for the backend they derive for
  themselves: the first of them to need one calls `_initbackend()` (under a
  lock, so two threads build one) and the rest then use that object, so 20
  children of a fresh root open one connection. A path built separately
  (`UriPath(url)` twice), one on another endpoint, the sourceless result of
  `relative_to()` and a path that holds a supplied backend are not in it.
  `with_backend(backend)` returns a copy using `backend`. A backend is only
  shared within one endpoint (scheme, userinfo, host, port): a join,
  `with_source()` or `UriPath(base, url)` onto another endpoint takes none
  and builds a fresh one on first use, so credentials and sessions never
  follow. When several joined paths hold one, the rightmost whose endpoint
  is the result's is taken; the sourceless result of `relative_to()` holds
  none, so `dst_root / src.relative_to(src_root)` uses `dst_root`'s.
  `_same_filesystem()`: two URIs are on different filesystems only when
  BOTH carry a backend the caller supplied (`backend=`, `with_backend()`,
  or inherited from such a path) and those are different objects -- two
  connections, or fakes standing in for two hosts. A backend a path built
  for itself counts as none, so two separately built paths to one URL are
  the same file. The path records that it built the backend and passes the
  record on, so this holds for any backend object, a `dict` or a slotted
  class without `__weakref__` included. A scheme that hands its own backend
  on through `backend=` (as a `with_source()` override does) is recognised
  as derived when the object is weakly referenceable (every built-in
  `Base*Backend` is) and `_initbackend()` built it.
  Copies: `pickle` holds the URI text (userinfo included, since that is the
  URI) and the `schemesmap`, and nothing else: no session headers, client
  kwargs or live client. A supplied backend goes along only if its class
  sets `picklable = True`; a derived one is built again on demand.
  `copy.copy()` and `copy.deepcopy()` share the backend object, supplied or
  derived, and never duplicate a connection. None of them carries the stat
  hint. `==`, `hash()`, `_same_filesystem()` and `_node_key()` answer as
  before, except that a pickle which dropped a supplied backend leaves a path
  with none, which `_same_filesystem()` cannot tell from another host's.
  A subclass with per-path state that is not a secret returns it from
  `_reduce_options()` (constructor keywords).
- Listing: implement `_listdir() -> Iterator[str]` or override
  `_scandir()`; `iterdir()` wraps each name with the entry's stat as a
  single-use hint (the child's first `stat()` returns it, later calls
  re-fetch). The default `_scandir()` skips a listed name that is not one
  path component; an override must do the same.
- `/` and `joinpath()` choose the result class from the scheme.
- `rename()`/`symlink_to()` take a `str` as an already-decoded path (`?`,
  `#`, `%`, `:` are filename characters); a relative `rename()` target is a
  sibling of `self`. A target on another endpoint (or another archive or
  Azure container) raises `NotImplementedError`, so `move()` copies and
  deletes.
- `copy()`/`move()` read a `str` destination **by its shape**: with a
  scheme (`ftp://host/key`, `data:,abc`) it is a URI, so a cross-scheme
  copy works; without one it is a decoded path on this endpoint — absolute
  replaces the path, relative is a sibling, as `rename()` resolves it — and
  keeps this path's source and backend rather than opening a second
  connection. A one-letter scheme is read as a drive, so `C:/Temp/x` is a
  decoded path: the Windows path of that name on a `file:` path, a relative
  sibling (`http://h/d/C:/Temp/x`) on any other scheme.

### `Source` (`uripath.source`)

```python
class Source(NamedTuple):
    def __init__(self, scheme, userinfo, host, port): ...
    def as_str(self, sanitize=True) -> str: ...
    @classmethod
    def from_str(cls, source, strict=True): ...
    def keys(self): ...
    def parsed_userinfo(self) -> tuple[str, str]: ...
    def get_scheme_cls(self, schemesmap=None): ...
    def is_local(self) -> bool: ...
```

`NamedTuple`,
falsy when all fields are empty; indexes by position, slice or field name.
`as_str(sanitize=True)` is the composer `Uri.as_uri()` uses (`file:` for an
empty host; an invalid scheme or port is a `ValueError`); `str()`/`repr()`
redact the password, and the whole userinfo for `github:`/`gitlab:`/`git:`
(the fields keep it). `Source.from_str(source, strict=True)` reads the
authority as `Uri` does (`ValueError` for a path/query/fragment when
strict, naming the component and never the input),
`parsed_userinfo() -> (user, password)` (`""` when absent; `userinfo`
stays the decoded `user:password` text),
`get_scheme_cls(schemesmap=None) -> type[UriPath]`, `keys()` (the field
names, so `dict(source)` works), `is_local()` —
`localhost`/empty host or an address of this machine (IP literal, or any
A/AAAA answer via `netimps`); the answer depends on the host alone and is
kept for 60 seconds for at most 256 hosts, so a miss does DNS.

### `Query` (`uripath.query`)

```python
class Query(str):
    ENCODING = "utf-8"
    SEPARATOR = "&"
    def __init__(self, query, *, encoding="utf-8", separator="&"): ...
    def decode(self) -> list[tuple[str, str | None]]: ...
    def to_dict(self, *, single=False): ...
```

`str` subclass holding the encoded query; built from a `str` (taken as
encoded and kept byte for byte), a mapping (a sequence value repeats the
key) or `(key, value)` pairs, which are encoded so that `decode()` returns
what was given: `+`, `=`, the separator, `#`, `%` and white space are
escaped (`{"sig": "ab+cd=="}` is `sig=ab%2Bcd%3D%3D`).
`decode() -> list[tuple[str, str | None]]` follows RFC 3986, not
form-urlencoding: only `%XX` escapes are decoded and a `+` stays a plus
(`urllib.parse.parse_qsl` reads form text). Iteration yields the decoded
pairs, `to_dict(*, single=False)`. `Query.ENCODING` (`"utf-8"`) and
`Query.SEPARATOR` (`"&"`) are the defaults of `encoding=` and `separator=`.

### For scheme implementers (`uripath`, `uripath.source`)

The names a `UriPath` subclass overrides or calls beyond `Uri` and `UriPath`
above, in one place: the built-in schemes use all of them, so they are
contract (the core hooks they also use are under "For path implementers").
The helpers were underscore names (`_same_authority`, `_DerivedBackend`,
`_compose_uri`, `_compose_host`, `_encode`, `_is_drive`, `_SAFE_PATH`,
`_ERRORS`); those spellings stay importable and are the same objects.

```python
class Uri(Pathname):
    def _init(self, source, path, query, fragment, **kwargs): ...
    def _from_parsed_parts(self, source, path, query, fragment, /, **kwargs): ...
    @classmethod
    def _format_parsed_parts(
        cls, source, path, query, fragment, /, sanitize=True,
    ) -> str: ...
    @classmethod
    def _parse_uri(cls, uri) -> tuple[Source, str, Query, str]: ...
    def _load_parts(self): ...
    def _make_child_relpath(self, name, **kwargs) -> Self: ...
    def _join_decoded(self, key) -> Uri: ...
    def _is_absolute_decoded(self, path) -> bool: ...
    def _rename_target(self, target) -> Uri: ...
    def _same_location(self, other) -> bool: ...
    _initiated
    _raw_uris
    _source
    _query

class UriPath(Uri, Path):
    def _init(self, source, path, query, fragment, /, backend=None, **kwargs): ...
    def _make_child_relpath(self, name, stat_hint=None, **kwargs) -> Self: ...
    def _pop_stat_hint(self) -> FileStat | None: ...
    def _listdir(self) -> Iterator[str]: ...
    def _backend_for(self, source): ...
    def _inherit_backend(self, source) -> None: ...
    def _supplied_backend(self): ...
    @classmethod
    def _schemes(cls) -> Sequence[str]: ...
    _backend
    _backend_derived
    _backend_candidates
    _derived_cell
    _schemes_in_use
    _stat_hint

def same_authority(a, b) -> bool: ...
class DerivedBackend: ...
```

```python
# uripath.source
def compose_uri(scheme, userinfo, host, port, path, query, fragment) -> str: ...
def compose_host(host) -> str: ...
def percent_encode(text, safe) -> str: ...
def is_drive(segment) -> bool: ...
SAFE_PATH = "!$&'()*+,;=:@/"
ERRORS = "surrogateescape"
```

Building and deriving a path:

- `_init(source, path, query, fragment, **kwargs)` — stores the decoded
  components; every constructor, join and `with_*()` ends here, and it may run
  again on a live instance. An override sets its own state, then calls
  `super()._init()`. `UriPath._init` also takes `backend=`, a backend the
  caller supplied.
- `_from_parsed_parts(source, path, query, fragment, /, **kwargs)` — a
  same-type instance from decoded components with no parsing (a `rename()`
  result, a probe); the keywords reach `_init()`.
- `_format_parsed_parts(source, path, query, fragment, /, sanitize=True)`
  — the URI text of decoded components (`sanitize` drops the password);
  `as_uri()` and `str()` call it, so a scheme with a different spelling
  overrides it. `_parse_uri(uri)` is its reverse for URI text: `(Source,
  decoded path, Query, fragment)`.
- `_load_parts()` — parses a path that was built from arguments and is not
  parsed yet; `source`, `path`, `query` and `fragment` call it. Call it
  before reading `_source`, `_query` or the backend state of a path that may
  still be waiting (`_initiated` is False; `_raw_uris` holds its arguments).
- `_make_child_relpath(name, stat_hint=None, **kwargs)` — the child called
  exactly `name` (one segment, never re-parsed); `iterdir()`, `_scandir()` and
  the `str` join build children with it, so a scheme that gives a name a
  meaning (`gitlab:`'s `-`) overrides it. `stat_hint` is the listing's stat
  for that child.
- `_join_decoded(key)` — joins an already-decoded path string name by name
  through `_make_child_relpath()`, dot segments resolved as RFC 3986 5.2.4
  says; an absolute key restarts at the root of the same source.
  `_is_absolute_decoded(path)` says whether a string restarts a join (a leading
  `/`; `FileUri` also a drive path).
- `_rename_target(target)` — a `rename()` destination as a `Uri`: a `str` is a
  decoded path, resolved against `self.parent`. Raises `NotImplementedError`
  when `_same_location()` says a native rename cannot reach it, which makes
  `move()` copy. `_same_location(other)` is True for the same endpoint
  (`same_authority()`) or a sourceless path; override it where the namespace
  is narrower than the authority (an archive, an Azure container).
- `_pop_stat_hint()` — the stat `_scandir()` attached to this child, once: a
  `stat()` that returns it saves the request, and the next call asks again.
  A type-only hint (`size_known` False) is consumed and not returned, so
  `stat()` asks the server; `is_dir()`, `is_file()`, `exists()` and
  `is_symlink()` of the child use it instead (`_st_mode()`), once. A scheme
  whose listing knows a file's type and not its size yields
  `FileStat(is_dir=False, size_known=False)` rather than `None`: `walk()`,
  `glob()` and `rm(recursive=True)` then cost one request per directory.
  `gitlab:` (blobs) and `http:` (an index without exact sizes) do.
- `_listdir()` — the names `_scandir()` lists by default; a stub.
- `_schemes()` — the scheme names this class registers.

Backend state (read it only in an override that changes how a path carries a
backend, as the archives and `git:` do):

- `_backend` is the backend object or `None`; `_backend_derived` says the path
  built it or inherited one that was built, not supplied;
  `_supplied_backend()` returns only a supplied one and builds nothing.
- `_backend_for(source)` — `(backend, derived)` this path hands a path at
  `source`: its own when `source` is its endpoint, else `(None, None)`.
  `_inherit_backend(source)` settles, once the endpoint is known, which
  joined segment's backend the path takes; call it first in an `_init()`
  override that reads `_backend`.
- `_backend_candidates` holds the join segments (with their backends) until
  then; `_derived_cell` is the slot shared by paths derived from one another
  on one endpoint (`None` for one that holds a backend or was not derived);
  `_schemes_in_use` is the `schemesmap=` the path was built with; `_stat_hint`
  is the pending hint.
- `same_authority(a, b)` — whether two `Source`s name one endpoint (scheme,
  userinfo, host, port; `""` and `None` alike): the test for letting a
  backend, a connection or a rename pass from one path to another.
- `DerivedBackend` — a base class for a backend that only `_initbackend()`
  creates and that cannot be weakly referenced (a tuple): without it, or
  `"__weakref__"` in `__slots__`, `_same_filesystem()` reads it as supplied.

Composing text:

- `compose_uri(scheme, userinfo, host, port, path, query, fragment)` — URI text
  from decoded components, each percent-encoded for its part; `None` omits one
  and an invalid scheme, port or path/authority pairing is a `ValueError`.
  `compose_host(host)` encodes a host (an IPv6 address is bracketed, an
  internationalized name is IDNA). `percent_encode(text, safe)` encodes UTF-8
  and keeps the characters of `safe`; `SAFE_PATH` is the set a path keeps.
  `ERRORS` is the error handler for percent-decoding and re-encoding
  (`"surrogateescape"`: a byte that is not UTF-8 survives the round trip).
- `is_drive(segment)` — whether a segment is a Windows drive (`"C:"`).

## Built-in schemes (`uripath.schemes`)

Every class is dispatched by `UriPath(...)`; `uripath.schemes`
re-exports `FileUri`, `DataUri`, `HttpPath`, `DavPath`, `FtpPath`, `GitHubPath`,
`GitLabPath`, `GitPath`, `ZipUri` and `TarUri` lazily. Backends are passed
as `UriPath(uri, backend=...)` or `path.with_backend(...)`.

### `FileUri` — `file:` (`uripath.schemes.file`)

```python
class FileUri(UriPath):
    filepath
```

`file:///abs`, `file:rel`,
`file://localhost/C:/x`. `filepath -> LocalPath`; all I/O delegates to it
(listing reuses `LocalPath`'s scandir). `rename()` accepts local targets
only and returns a `FileUri`. No `symlink_to()`/`readlink()`. On Windows a
drive is the anchor: `parents` ends at the drive root (`file:/C:/`) and
equals the repeated `parent`, dot segments never climb above it, and a
`str` join key or `copy()`/`move()`/`rename()` destination reads `\` as a
separator (`C:\Temp\x` is an absolute path). A path with a named host is a
UNC path there, whose anchor is the share: `file://server/share/a/b` has the
ancestors `file://server/share/a` and `file://server/share/`, and the share
root is its own parent. A `FileUri` argument holding a drive
(`base / UriPath("file:///D:/f")`) restarts the join, as a `str` key does.
Elsewhere a backslash is a filename character and the root of a host is the
end of the chain, and every other scheme splits on `/` only.

### `DataUri` — `data:` (`uripath.schemes.data`)

```python
class DataUri(UriPath):
    mediatype: str
```

RFC 2397
`data:[<mediatype>][;base64],<data>`. `mediatype` property (default
`text/plain;charset=US-ASCII`). RFC 2397 has no query: an unescaped `?` and
what follows it are payload (`data:,a?b` reads `a?b`), while a `#` starts the
fragment. Read-only single file: `open("r")` only,
`stat().st_size` is the decoded size, listing → `NotADirectoryError`.

### `HttpPath` — `http:`, `https:` (`uripath.schemes.http`)

```python
class HttpPath(UriPath):
    def with_transport(
        self, transport, *, headers=None, timeout=(10, 60),
        write_method="PUT", append_mode="rewrite",
    ): ...
    def with_session(
        self, session, write_method="PUT", append_mode="rewrite",
        **requests_args,
    ): ...
    def stat(self, *, follow_symlinks=True, walk_up_last_modified=False): ...

class HttpBackend:
    def __init__(
        self, transport=None, *, headers=None, timeout=(10, 60),
        write_method="PUT", append_mode="rewrite",
    ): ...
    def request(
        self, method, uri, *, data=None, headers=None, stream=False,
        allow_redirects=None, timeout=...,
    ): ...
    def close(self): ...

class HttpWriteStream(BytesIO): ...
class HttpAppendStream(BytesIO): ...

DEFAULT_TIMEOUT = (10, 60)
MAX_LISTING_BYTES = 8388608
```

HTTP needs no library: a path sends through a
**transport**, by default the built-in `HTTPTransport` on `http.client`.

```python
class HTTPTransport:
    def __init__(self, *, ssl_context=None, verify=True, proxies=None): ...
    def send(
        self, method, url, *, headers, body=None, timeout, stream=False,
    ): ...
    def close(self): ...

class HTTPResponse:
    status: int
    reason: str
    headers: Mapping[str, str]
    url: str
    def __init__(
        self, status, reason, headers, url, body=b"", *, decode=True,
    ): ...
    def read(self, size=-1): ...
    def iter_bytes(self, chunk_size=65536): ...
    def close(self): ...
```

- **The transport contract.** Any object with `send(method, url, *, headers,
  body=None, timeout, stream=False) -> HTTPResponse` and `close()` is a
  transport (a context manager is optional). `send()` makes exactly one
  request: it follows no redirect, adds no credentials and retries nothing
  but what is stated below. `body` is `None`, `bytes`, a binary file or an
  iterable of `bytes` (never `str`: `TypeError`). A body is sent under a
  `Content-Length` when its length is known without reading it: `bytes`, a
  list or tuple of `bytes`, a file that is seekable (the bytes from `tell()`
  to its end, the position restored) and a regular file (its size less
  `tell()`). Any other body (an iterator, a generator, a pipe or another
  stream that cannot report its size) is sent `Transfer-Encoding: chunked`.
  Both transports send the same. A `Content-Length` in `headers` is trusted:
  that many bytes are sent and nothing is chunked, a longer body is cut
  there, a count that is not a number or is larger than a body whose length
  is known is `ValueError` before anything is sent, and a body that runs out
  first is `OSError(EIO)` with its connection closed. No body is sent past
  its length (a file that grew after it was measured is cut there). A file or
  iterator is never rewound and never sent twice, whatever its length is
  known to be. `timeout` is seconds, a
  `(connect, read)` pair or `None` (no limit); the read half bounds each wait
  on the server, not the whole reply. With `stream=False` the body has been
  read when `send()` returns; with `stream=True` it is read from the
  response, which the caller closes (an unread rest of a body closes its
  connection). A transport raises only `TimeoutError`, `ConnectionError`,
  `ssl.SSLError`, `ValueError` (before anything is sent, for a header or URL
  with a control character, a URL with credentials, or another scheme) or
  else `OSError(EIO)`; no third-party exception and no URL or header value is
  in its text. A reply below 200 is never the one `send()` returns:
  `HTTPTransport` skips interim (1xx) replies, at most 8, and past that is
  `OSError(EIO)` with its connection closed.
- **`HTTPResponse`**: `status`, `reason`, `headers` (read-only, names compare
  without case, a name sent twice reads as `"a, b"` and `headers.get_all()`
  lists them), `url` (the URL requested, without fragment; an empty path is
  `/`), `read(size=-1)`, `iter_bytes(chunk_size)`, `close()` and a context
  manager. A `gzip` or `deflate` body is decoded, in steps of at most 256
  KiB of output per step, unless the request set an `Accept-Encoding` naming
  a coding of its own (`identity` counts as none); `headers` stay as
  received, so `Content-Length` counts the encoded bytes. A body that ends
  before the length the server stated, a chunked body cut short, and a coded
  body that is not valid are `OSError(EIO)`, never a shorter read. A
  transport builds one from `bytes` or from an object with `read(amount)` and
  `close()`; a fake transport in a test does the same.
- **`HTTPTransport(ssl_context=None, verify=True, proxies=None)`** is
  standard library only. `https:` is verified against `ssl_context`, else
  against `ssl.create_default_context()` (the system trust store, not
  certifi); `verify=False` is the one way to turn verification off, and
  `ssl_context` wins over it. Each thread keeps one idle connection per
  server (at most 8, closed when the thread ends or on `close()`), reused for
  its next request unless the server has closed it or sent bytes on it since
  (checked before anything is sent). A request that fails before any byte of a reply on a
  reused connection that the server had closed is sent once more on a new
  connection **only** if it is `GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE` or
  `PROPFIND` and its body is `None` or in memory; any other request uses an
  idle connection only if it carried a reply within the last second. A
  timeout is never retried. `stream=False` holds the whole body in memory;
  read a body that may be large with `stream=True`.
- **Proxies.** `proxies=None` reads the environment (`HTTP_PROXY`,
  `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, through `urllib.request`, which
  matches names and suffixes in `NO_PROXY`; a CIDR block there, such as
  `10.0.0.0/8` or `fd00::/8`, also sends an IP-literal host direct, and a
  host name is never resolved to be matched against one).
  Otherwise `proxies` is indexed with the request URL (no fragment): it
  returns `None` (direct), one proxy, or an iterable of them to try in order
  when a connection cannot be made (`None` in the order is a direct
  attempt, and an empty iterable is direct as well); `KeyError` means direct
  and the environment is not read; `{}` sends everything direct (unlike
  other clients, which still read the environment); an exception of the
  provider other than `KeyError` reaches the caller as it is. A proxy is a `str` URL or any object with a `url`
  attribute, so a proxy resolver from another library works as it is, with
  none imported here:

  ```
  class Resolver:  # tries the first proxy, then connects directly
      def __getitem__(self, url):
          return ["http://user:secret@proxy.example:3128", None]

  transport = HTTPTransport(proxies=Resolver())
  ```

  A plain `dict` may use the keys the `requests` library
  does (`"http"`, `"https"`, `"all"`, `"scheme://host"`). Only `http://`
  proxies work: absolute-form requests for `http:` and `CONNECT` for
  `https:`, with `Proxy-Authorization: Basic` from the proxy URL's userinfo
  (sent to the proxy only); any other scheme (`socks5`, `https`) is
  `OSError(EPROTONOSUPPORT)` naming the scheme and `uripath-http-requests`. A
  proxy that refuses `CONNECT` is a `ConnectionError` and the next proxy is
  not tried. Proxy credentials are in no message, `repr()` or traceback.
- **Choosing the transport.** `path.with_transport(transport, headers=None,
  timeout=(10, 60), write_method="PUT", append_mode="rewrite")` installs a
  backend over any transport (the caller closes it). `path.with_session(
  session, ...)` is the same over a `requests.Session`; that transport is
  provided by `uripath-http-requests`, and without it the call raises
  `ImportError` naming it. Without either, a path's backend builds the
  built-in transport on first use (`HttpBackend.close()` or leaving its
  `with` block closes a transport the backend built); the environment variable
  `PATHLIB_NEXT_HTTP_TRANSPORT` (`builtin` or `requests`) names that default
  for the process. `HttpBackend` is a class, no longer a named
  tuple: `HttpBackend(transport=None, *, headers=None, timeout, write_method,
  append_mode)`.
- **What the backend does for every transport.** It follows redirects, adds
  credentials and default headers (`User-Agent: pathlib-next`, `Accept: */*`),
  applies the default timeout, and maps a status to a pathlib exception.
  `headers` given to the backend go with every request; request-specific
  headers merge over them by name (case-blind). A header value or URL with a
  control character (CR and LF included) is `ValueError`, before anything is
  sent. A reply it needs whole (a PROPFIND's, a git API's JSON,
  `request(stream=False)`'s) may be at most `MAX_LISTING_BYTES` after
  decoding, however small it is on the wire: more is `OSError(EFBIG)` naming
  the path, and the connection is closed. A reply whose body nobody looks at
  (a write's, a DELETE's, an error's) is read up to that many bytes and
  dropped, so its connection can be reused when the body was short. The
  content of a file (`open("r")`, a git file) is not limited.
- Timeout: `DEFAULT_TIMEOUT = (10, 60)` (connect, read) unless given;
  `timeout=None` waits forever.
- Redirects: `GET`/`HEAD`/`OPTIONS` follow up to 30 (a `303` becomes a
  `GET`); a redirect whose `Location` is missing or that a request cannot be
  sent to (another scheme, a port out of range, a host that is not a name) is
  `OSError(EIO)` naming the status, never `ValueError`, which is reserved
  for the caller's own URL and headers. A
  redirect that changes the scheme, host or port drops `Authorization` for
  every later hop, the asking again of `stat()`, `exists()`, `is_dir()`,
  `unlink()`, `open("x")` and a patch-mode append included (also on a
  redirect from `https:` to `http:`), and nothing else: headers
  other than `Authorization` from `with_transport(headers=...)` (`X-Api-Key`,
  a vendor token header, a cookie) are sent to the new host as well, even to
  a plain `http:` one, so keep a secret in `Authorization`, or point the path
  at the final URL. Every other request
  (`PROPFIND`, `write_method`, `PATCH`, `DELETE`, `MKCOL`, `MOVE`) is sent
  without following: a 307/308 (for `PROPFIND` also a 301, 302 or 303) to the
  same scheme, host and port is re-sent once with the same method, headers
  and body; any other 3xx, another origin or a second redirect raises
  `OSError(EIO)` naming the status and the `Location` (userinfo and query
  removed). A body that is not `bytes` cannot be re-sent, so it raises too.
- URL userinfo is sent as `Authorization: Basic` (not in the URL) unless
  `headers` or the call name an `Authorization`. Percent-escapes stand for
  octets, and those octets are the credential: `caf%C3%A9` is sent as UTF-8
  bytes, `%FF` as the byte `FF`. The built-in transport never reads
  `~/.netrc`.
- `stat()` — `HEAD`
  (`GET` on 405); a redirect is followed once, at its `Location`; a final
  URL whose path ends in `/` is a directory (a query or fragment does not
  matter); `st_size` from `Content-Length` (absent, non-numeric or negative
  = unknown, `0`), `st_mtime` from `Last-Modified` (UTC), or from the
  parent's index when `walk_up_last_modified=True`.
- An index page prints its dates with no zone, and they are read as UTC:
  the `st_mtime` of a listed entry can be off by the server's offset from
  UTC (`stat()` of the entry uses `Last-Modified`, which names its zone).
  Compare sizes, or give `PathSyncer` `quick_check=False`.
- Listing scrapes an Apache/nginx-style HTML index, asking for the
  directory's URL with a trailing `/` first; `.`/`..` rows are never
  children; a non-HTML response → `NotADirectoryError` (an HTML file lists
  as empty). Cannot always tell a file from an index page. The body is read
  like `open()` reads a file: a cut-short, stalled or undecodable one is
  `OSError(EIO)`/`TimeoutError` naming the path, never a partial list, and
  one over `schemes.http.MAX_LISTING_BYTES` (8 MiB after decoding; assign a
  larger number to allow more) is `OSError(EFBIG)`. A name that is not
  UTF-8 (`caf%E9`) keeps its bytes (`surrogateescape`) and is requested as
  listed.
- `open("r")` streams `GET` with `Accept-Encoding: identity`; the mode is
  matched exactly, so `"r+"`, `"w+"` and `"a+"` raise `NotImplementedError`.
  `"w"`/`"x"` (an `HttpWriteStream`)
  buffer and send `write_method` on close. `"x"` first calls `stat()`: found
  → `FileExistsError`, a failure other than not-found raises with nothing
  sent; the upload then carries `If-None-Match: *`, and a 412 reply →
  `FileExistsError` (a server that ignores the header leaves the window
  between probe and upload open). `"a"` (an `HttpAppendStream`):
  `append_mode="rewrite"` (GET + full
  re-upload, not atomic) or `"patch"` (`PATCH` with `Content-Range` from the
  `HEAD` size; a `HEAD` reply without `Content-Length` → `OSError(EIO)`
  naming the path, nothing sent; a refusal raises `PermissionError` for
  401/403/405/501, `OSError(EIO)` for other statuses). An `open("a")` that
  raises (the read of the current content, or the `HEAD` of patch mode,
  failed) has uploaded nothing.
- `unlink()` sends `DELETE` and refuses a directory (`IsADirectoryError`,
  judged by `stat()`); `rmdir()` requires an empty directory. No `mkdir()`,
  `rename()`, `chmod()`.
- Status mapping: 404/410 → `FileNotFoundError`, 401/403/405/501 →
  `PermissionError`, 409 → `FileExistsError` (`FileNotFoundError` for
  writes), other → `OSError(EIO)` with the status. A transport's
  `TimeoutError` and `ConnectionError` are re-raised naming the path, with
  no cause. Text that came from the server and goes into a message (a reason
  phrase, a `Location`, a rate-limit header, the `href` of a failed `DavPath`
  member) is shown with control, line-separator and bidirectional characters
  escaped (`\x1b` for ESC) and cut to 120 characters (200 for a URL).

### `DavPath` — `dav:`, `davs:` (`uripath.schemes.dav`)

```python
class DavPath(HttpPath):
    def stat(self, *, follow_symlinks=True, walk_up_last_modified=False): ...
```

Same backend, `with_transport()` and `with_session()`. `stat()`/
listing via `PROPFIND` (`stat()` takes `walk_up_last_modified=` and ignores
it: the reply carries the modification time). A reply that is not a
`multistatus` document, or that names neither the collection nor any
member of it, is `OSError(EIO)`; a listing keeps a member only when its
href, resolved against the collection, names the same host and a direct
child, and a `getcontentlength` that is not a plain number is unknown (`0`).
`open("r")` on a collection → `IsADirectoryError`;
`"w"`/`"x"` send `write_method` (default `PUT`) on close (`"x"` as for
`HttpPath`, probing with `PROPFIND`); `"a"` unsupported, so `append_mode`
has no effect. `mkdir()` = `MKCOL`
(missing parent → `FileNotFoundError`). `unlink()` refuses a collection;
`rmdir()` checks emptiness first; `rm(recursive=True)` is one recursive
`DELETE` (failed members of a 207 raise). `rename()` = `MOVE` with
`Overwrite: F` (existing target → `FileExistsError`), no credentials in
`Destination`, which carries the target's own query (never the source's)
and no fragment. 423 → `PermissionError`. `PROPFIND`, `PUT`, `MKCOL`, `DELETE`
and `MOVE` follow the `HttpPath` redirect rule above (a listing is scoped to
the URL that answered it). No `chmod()`.

### `FtpPath` — `ftp:`, `ftps:` (`uripath.schemes.ftp`)

```python
DEFAULT_TIMEOUT = 30.0
IDLE_PROBE_SECONDS = 1.0

class FtpBackend(BaseFtpBackend):
    timeout
    ssl_context
    verify
    def __init__(
        self, timeout=30.0, ssl_context=None, verify=True,
    ) -> None: ...

class BaseFtpBackend:
    def client(self, source, tls) -> _ftplib.FTP: ...
```

- `FtpBackend` — `timeout`
  bounds connect, replies and transfers (`None` = forever). `ftps:` is
  explicit TLS with `PROT P`; the certificate and host name are verified
  with `ssl.create_default_context()`; `ssl_context` (e.g.
  `ssl.create_default_context(cafile=...)`) wins over `verify`;
  `verify=False` accepts any certificate. Data connections reuse the TLS
  session. No user in the URI → anonymous login.
- `BaseFtpBackend.client()` — override to supply
  connections.
- Paths without `backend=` share one default `FtpBackend()`. Connections
  are cached per (backend, source, tls, thread) (LRU of 128, closed on
  eviction, and closed when their thread ends). A connection that carried
  a command within the last `schemes.ftp.IDLE_PROBE_SECONDS` (1 second, the
  `pathlib_next.ftp` constant) is used as it is; one idle for longer, or not
  yet used, is probed with `NOOP` and replaced when dead.
- `FtpPath` is a `UriPath` over `pathlib_next.ftp.FTPPath`: the listing,
  stat, reads, writes, `rename()`, `chmod()` and `_utime()` are those
  described under "What a path does" in the FTP section, and an `OSError`
  names the URI. Its URI-only parts are the endpoint (the `Source` and the
  scheme's `tls`) and the backend rules above.
- An empty path (`ftp://host`) is the root, as `ftp://host/` is: `/` is
  sent in every command that takes a path, never an empty argument (which a
  server reads as its working directory).

### `GitHubPath` — `github://[TOKEN@]host/owner/repo/path?ref=REF` (`uripath.schemes.github`, `uripath.schemes._gitrepo`)

```python
class GitHubPath(UriPath):
    owner: str
    repo: str
    repo_path: str
    ref: str | None

class RepoBackend(BaseRepoBackend):
    def __init__(
        self, token=None, session=None, api_base=None, *, transport=None,
        headers=None, timeout=(10, 60), **requests_args,
    ): ...
    def close(self): ...

class BaseRepoBackend:
    def request(self, method, url, headers=None, params=None, **kwargs): ...
```

Read-only; `open()` other than `"r"` and every
write method raise `NotImplementedError`.

- Properties: `owner`, `repo`, `repo_path`, `ref` (`None` = default
  branch); `?ref=` is carried to every child.
- `RepoBackend` (`schemes.github`; `BaseRepoBackend` is in `schemes._gitrepo`): `Authorization: Bearer <token>`, timeout default
  `(10, 60)`, `cache` dict; `api_base` overrides the API root;
  `BaseRepoBackend.request(method, url, headers=None, params=None, **kwargs)`
  is the override point and returns an `HTTPResponse`.
  A request that carries `Authorization` (the token, or one given in
  `headers=`) to a plain `http://` URL on a host other than loopback is
  still sent, with an `InsecureTransportWarning` (a `UserWarning`,
  importable from `schemes._gitrepo`, `schemes.github` and
  `schemes.gitlab`).
  Without `backend=`, the token is the userinfo password
  (`x-access-token:TOKEN@`) or else the bare user (`TOKEN@`).
- `str()`, `repr()`, `as_posix()` and `as_uri(sanitize=True)` drop the whole
  userinfo. Owner, repository and every path segment are percent-encoded
  into the API URL, so none can add a query or a segment, and a `.` or `..`
  segment in the path or the ref (made with `with_name("..")` or
  `with_path()`; a URI's own dot segments are already resolved) raises
  `ValueError` instead of leaving the repository's API root.
- API root `https://api.github.com` for `github.com`, else
  `https://host[:port]/api/v3`. Contents API listings (a directory at the
  1,000-entry cap is re-read through the Git Trees API); file bodies use
  the raw media type; symlink/submodule entries read as files;
  `st_mtime` is `0`.
- `stat()`, `exists()` and `is_file()` of a file are one `HEAD` of the
  contents URL asked for the raw media type and unencoded: the size is its
  `Content-Length`, and a `404` there is `FileNotFoundError`. A directory
  answers with a JSON type and is then listed with a `GET` (two requests;
  the root of the repository is listed directly). A `HEAD` reply without
  `X-GitHub-Media-Type` (a proxy's, a server that refuses `HEAD`), with an
  encoding, or without a plain `Content-Length` is not used: the `GET` of
  the contents object answers, as it did.
- Rate limits (403/429 with limit headers, any 429) → `OSError(EAGAIN)`.
- A JSON reply that is not the documented shape (HTML from a proxy, `null`,
  a truncated body, an array where an object is expected, an entry without
  a name and a type, a size that is not a non-negative integer) is
  `OSError(EIO)` naming the path, so `exists()` is `False` and `stat()`
  raises. A raw file body has no shape to check and is returned as sent,
  except a `200` whose `Content-Type` is `text/html` and that carries no
  `X-GitHub-Media-Type` header: the API names its media type in every
  reply, so that is a proxy's or a captive portal's page, and `open()` of
  it is `OSError(EIO)` naming the path (a file of the repository that is
  HTML still reads, with the header). That rule has not been checked
  against the live service.

### `GitLabPath` — `gitlab://[TOKEN@]host[:port]/owner/repo/path` (`uripath.schemes.gitlab`)

```python
class GitLabPath(UriPath):
    owner: str
    repo: str
    repo_path: str
    ref: str | None
```

Same backend, properties and read-only
contract; API root `https://host[:port]/api/v4` (`gitlab.com` by
default). Without `?ref=` the default branch is fetched once
(`GET /projects/:id`) and cached in `backend.cache`. Tree listings are
paginated (100 per page); a blob entry is a type-only hint
(`size_known=False`), so `walk()`, `glob()` and `rm(recursive=True)` cost one
request per directory; the `stat()` of a file is a `HEAD` of the files
endpoint reading `X-Gitlab-Size` (a reply without it, or a refused `HEAD`, is
followed by a `GET` of the file's metadata); `st_mtime` is `0`. Replies of the wrong shape are
`OSError(EIO)` as for `GitHubPath`.

### `GitPath` — `git:` (`uripath.schemes.git`)

```python
class GitPath(UriPath): ...
class GitHubGitPath(GitHubPath): ...
class GitLabGitPath(GitLabPath): ...
```

`git://github.com/...` constructs a
`GitHubPath`, `git://gitlab.com/...` a `GitLabPath`; any other host →
`ValueError`. `git+github:` (`GitHubGitPath`) and `git+gitlab:`
(`GitLabGitPath`) pin the provider for any host.

### Archives — `zip:`, `tar:`, `archive:` (`uripath.schemes.archive`, `uripath.schemes.archive._base`)

```python
MEMBER_SPOOL_BYTES = 16777216
MAX_LINKS = 40

class ArchiveUri(UriPath):
    def refresh(self) -> None: ...
    def batch(self) -> ContextManager[None]: ...
    def readlink(self) -> LinkTarget: ...
class LinkTarget(PurePosixPath):
    path: str
class ZipUri(ArchiveUri): ...
class TarUri(ArchiveUri): ...
ArchiveZipUri = ZipUri
ArchiveTarUri = TarUri
```

`ZipUri` (`zip:`), `TarUri` (`tar:`),
`ArchiveUri` (`archive:`, detects the format from the outer name
`.zip`/`.jar` vs `.tar`/`.tgz`/`.tar.*`, else a `PK` magic sniff),
`ArchiveZipUri` (`archive+zip:`), `ArchiveTarUri` (`archive+tar:`). The last
two are second scheme names of `ZipUri` and `TarUri`, and the class names
are aliases of those (`ArchiveZipUri is ZipUri`); a path prints and pickles
with the scheme it was written with.

- `archive:` settles the format on first use, not when the path is built:
  constructing, printing, joining, copying and pickling a path read nothing,
  a non-local outer that had to be read to decide is not fetched a second
  time, and a failure to read the outer propagates and decides nothing, so
  the next call tries again.
- Syntax `<scheme>:<archive-uri>!/<member>`; `<archive-uri>` must carry a
  scheme (`ValueError` otherwise) and may be any URI, including another
  archive (each leading archive scheme consumes one `!/`; nested archives
  are read-only). A member name containing `!/` is written `%21/`.
  `name`/`parent`/`glob()` work on the member path; `as_uri()`
  percent-encodes it, and a name that is not valid UTF-8 (a tar member
  written in another charset, held as surrogate escapes) keeps its bytes as
  `%XX` (`caf%E9.txt`), so such a path prints, hashes, compares and parses
  back to the same member.
- One shared handle per archive (keyed by the real local path, or the outer
  URI), released when no path references it. `ArchiveUri.refresh()` forgets
  what is held of the outer, so the next use reads it again; the rest is
  described under `ArchivePath`.
- `ArchiveUri` is a `UriPath` over `pathlib_next.archive.ArchivePath` (`ZipUri`
  over `ZipPath`, `TarUri` over `TarPath`) on the shared handle of its outer:
  member names, the archive root, links, cost, writes, `batch()`, the removal
  and the damage errors are those described under "Archives
  (`pathlib_next.archive`)", with an `OSError` naming the URI.
  `schemes.archive._base.MEMBER_SPOOL_BYTES` is the same setting as
  `pathlib_next.archive.MEMBER_SPOOL_BYTES`.

## Provided by other distributions

`uripath` knows these schemes and this transport by name and does not contain
them:

| Name | Distribution | Install |
| --- | --- | --- |
| `sftp:` | `uripath-sftp` | `pip install "uripath-sftp[paramiko]"` (or `[asyncssh]`) |
| `s3:`, `gs:`, `az:` | `uripath-objstore` | `pip install "uripath-objstore[s3]"` (or `[gs]`, `[az]`) |
| the `requests` HTTP transport | `uripath-http-requests` | `pip install uripath-http-requests` |

A path of one of the schemes builds, joins, compares and prints without its
distribution, and is listed by `UriPath.schemes()`. Every operation that needs
the server (`stat()`, `exists()`, `open()`, `iterdir()`, a write, `rename()`,
`chmod()`, ...) raises `ImportError`, with a message that names the scheme and
the install command and never the URI (it can carry a password). So does
`UriPath.scheme_class(name)`. The installed distribution registers its own
class for the name, through an entry point of the group `uripath.schemes`, and
that class is used.

For the `requests` transport, `HttpPath.with_session()`, a
`RepoBackend(session=...)` or `RepoBackend(**requests_args)` and
`PATHLIB_NEXT_HTTP_TRANSPORT=requests` raise `ImportError` naming
`uripath-http-requests`.

## Exceptions

### Warnings (`uripath.schemes.github`)

```python
class InsecureTransportWarning(UserWarning): ...  # also in schemes.gitlab
```

Unsupported
operations raise `NotImplementedError`. Network errors map to pathlib types
(`FileNotFoundError`, `PermissionError`, `FileExistsError`,
`IsADirectoryError`, `NotADirectoryError`, `OSError(ENOTEMPTY)`), timeouts to
`TimeoutError`, anything else to `OSError`; transport exceptions are not
chained (their text can carry credentials).

`InsecureTransportWarning` is the warning a `RepoBackend` gives before it
sends an `Authorization` header over plain `http://` (see `GitHubPath`).

## Command line

### `uripath` (`uripath._oldcli`, URI layer)

```python
def main(argv=None, *, stdin=None, stdout=None, stderr=None) -> int: ...
def build_parser() -> argparse.ArgumentParser: ...
```

Console script `uripath` = `uripath._oldcli:main`.
`main()` returns the
exit status and never raises `SystemExit`; `stdin` and `stdout` are binary
streams, `stderr` is a text or a binary stream (defaults: the process's), and
the usage and help text of the parser go to the process's own stderr and stdout;
`build_parser()` returns the `argparse` parser. An argument with `://`, or with a
scheme some class registers (`data:`, `zip:`, ...), is a `UriPath`; everything
else (including `C:/x` and `notes:draft`) is a `LocalPath`. `-` is stdin/stdout
where bytes are read or written.

| Subcommand | Arguments and flags |
| --- | --- |
| `read PATH` | Copy `PATH`'s bytes to stdout in chunks. |
| `write PATH [DATA] [--encoding utf-8]` | Write `DATA` encoded, or stdin's bytes when omitted. |
| `rm PATH [-r/--recursive] [--missing-ok] [--ignore-error]` | `Path.rm()`. |
| `cp SOURCE TARGET [-r/--recursive] [--overwrite] [--no-follow-symlinks] [--no-preserve-metadata]` | `Path.copy()`; with `-`, streams (an existing target needs `--overwrite`; no `-r`). |
| `sync SOURCE TARGET [--dry-run] [--remove-missing] [--size-only] [-v/--verbose] [--no-follow-symlinks] [--no-follow-mounts]` | `PathSyncer` with content comparison; `--size-only` compares sizes. `--dry-run` prints `would copy SRC -> DST`/`would remove`/`would mkdir`/`would replace`/`would symlink`; `-v` prints the changes made. `--no-follow-mounts` fails (exit 1, `OSError(EXDEV)`) on a mount point inside TARGET instead of syncing into it. |

Exit status: 0 success (also `--help`); 1 the operation failed, with one line
`uripath: <Type>: <message>` on stderr; 2 a wrong invocation, with the usage on
stderr (a missing or unknown argument, `cp -r` with `-`, an unknown
`--encoding`); 130 Ctrl-C; 141 the reader of stdout went away, quietly (on
Windows too, where a closed pipe reports `EINVAL`).

## Environment variables

### `PATHLIB_NEXT_HTTP_TRANSPORT` (URI layer)

`builtin` (the default when unset) or `requests`: the transport that `http(s):`,
`dav(s):`, `github:`, `gitlab:` and `git:` build for a backend that was not
given one (`HTTPTransport`, or the `requests` transport of
`uripath-http-requests`; without that distribution `requests` raises
`ImportError` naming it). The value is case-sensitive, and an empty or
unrecognised one raises `ValueError` naming the choices. It is read when a
backend first needs its transport, once per backend, so a change reaches
backends built afterwards. `with_transport()` and `with_session()` do not read
it.

## Gotchas

Importing `uripath` and constructing a path of any scheme does no I/O. A path
joins, compares and prints without touching a server; the first operation that
needs one (`exists()`, `stat()`, a read, a listing, `is_local()`) connects.
That holds for the schemes another distribution provides as well: without the
distribution their paths join, compare and print, and the first operation that
needs the server raises `ImportError`.
