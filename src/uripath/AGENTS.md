# `uripath` — public API header

Header-file-style reference for the `uripath` package: every public export with
its signature, arguments, contract and gotchas, so the package can be used
without reading its source. It ships inside the package and is
self-contained. Development documentation lives with the source at
<https://github.com/jose-pr/uripath>.

Names are imported from the module named in the heading of the section that
documents them. The root `uripath` exports `URI`, `URIPath`, `URILike`,
`Source`, `Query`, `QueryLike`, the functions `as_path` and `copy_stream`, the
errors `URIPathError`, `URISyntaxError` and `UnsupportedSchemeError`, and
`__version__`; the other public modules are
`uripath.source`, `uripath.query`, `uripath.exceptions` and `uripath.schemes`
(the contract a scheme implements, the registry, and the names every scheme
exports). The HTTP transport that `http:` and `dav:` send through is
`pathlib_next.http`, documented in the `pathlib-next` header. A module or name
that starts with an underscore is private and nothing there is contract: every
scheme lives in a private module.

`pip install uripath`. Required dependencies: `pathlib-next>=0.10.0,<0.11` and
`netimps>=0.4.0,<0.5`; parsing and percent-coding use only the standard library
(`urllib.parse`), and `netimps` is imported where it is used. The one extra, `cli`
(`duho>=0.7.3,<0.8`), adds the `uripath` command ("Command line"); every scheme
in this package runs on the standard library and on `pathlib_next`. `sftp:`,
`s3:`, `gs:` and `az:` are provided by other distributions ("Provided by other
distributions"), and so is the `requests` HTTP transport.

`uripath.__version__` is the version of the installed distribution, read from
its metadata. The rendered documentation is at
<https://jose-pr.github.io/uripath/> and the project overview is the
`README.md` shipped next to this file (`uripath/README.md`).

## URIs (`uripath`)

The URI layer builds on `Path` and `Pathname` of `pathlib_next`: the method
surface of `Path` (`read_text()`, `iterdir()`, `glob()`, `walk()`, `copy()`,
`move()`, `rm()`, ...) is that of the `pathlib-next` header. The classes are
`pathlib`-shaped: their method names, signatures and exception types are those
of `pathlib.Path`, and every deliberate difference is listed, with its
rationale, at <https://jose-pr.github.io/uripath/divergences/>.

### `URI`

```python
class URI(Pathname):
    def __init__(self, *uris, **options): ...
    source: Source
    path: str
    query: Query
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
(`str`, `bytes`, `URI`, `pathlib`/`pathlib_next` paths, `os.PathLike`;
`None` and `""` are the empty URI, anything else is a `TypeError` naming its
type) join right to left like `joinpath` (an absolute one restarts); this is not RFC
3986 reference resolution (`URI("http://h/d") / "x"` is `http://h/d/x`),
but the dot segments of the joined path are removed as RFC 3986 5.2.4
says: `URI("http://h/d/", "../x")`, `URI("http://h/d/") / "../x"`,
`URI("http://h/d/") / URI("../x")` and `URI("http://h/d/../x")` are all
`http://h/x`, and `URI("http://h/d/x") / ".."` is `http://h/d/`. A `..`
that would pass the root of an absolute path is dropped; a relative path
keeps its leading `..` (`URI("a") / "../../x"` is `../x`). A
percent-encoded dot segment (`%2e%2e`) is removed after decoding. An
absolute local path **object** (`pathlib.Path`, `LocalPath`) becomes
`file:`; a relative one joins like a `PurePath`. A `str` argument is always
URI text: wrap a path string (`LocalPath(s)`), because `URIPath("/abs/x")`
is a path with no scheme whose I/O raises `NotImplementedError` and
`URIPath("C:/Temp/x")` has the scheme `c`. `URI` takes no keyword argument
(`**options` is for the subclasses: see `_OPTIONS`).

- Properties: `source -> Source`, `path -> str` (percent-decoded),
  `query -> Query` (**percent-encoded as received**, sent unchanged; empty
  when there is none; not a `str`: compare `str(uri.query)`), `fragment -> str` (`""` when there is none),
  `parts -> (source, path, query, fragment)` (not path
  segments; use `segments`), `normalized_path`, `segments`, `parent`
  (`http://h/a` → `http://h/`; a trailing `/` is kept, so
  `URI("http://h/d/").name == ""`).
- Methods: `as_uri(sanitize=False)`, `with_source()`, `with_path()`,
  `with_segments()`, `with_query(QueryLike | None)` (a `str` is taken as
  already encoded; `None` removes the query), `with_fragment()`. `with_path(path)` gives a relative path under an
  authority the leading `/` the constructor gives it; `with_segments(*segments)`
  joins the spelling `segments` returns (a leading `""` is the root) with `/`,
  and an element may be `str`, `bytes`, a `PurePath` or an `os.PathLike`.
  `is_absolute()` (path starts with `/`),
  `is_relative_to(other)`, `relative_to(other, *, walk_up=False)`
  (`http://h` counts as the root), `is_local()`
  (`Source.is_local()`), `as_posix()` (`user@host:path` when a host is
  present).
- Query and fragment: every derivation that changes only the path keeps the
  query and the fragment of the path it starts from, so
  `p.parent / p.name == p`. That is `/` and `joinpath()` with a `str`
  (whatever the key: nested, dotted, absolute, with empty segments),
  `parent`, `parents`, `with_name()`, `with_stem()`, `with_suffix()`,
  `with_segments()`, `with_path()`, `relative_to()`, and the children that
  `iterdir()`, `glob()`, `rglob()` and `walk()` yield. A `URI` argument is
  joined as the constructor joins it: the last segment that sets a query (or a
  fragment) decides. The exception is a listing whose entries are named by
  the server: a child of an `http:` or `dav:` directory is its `href` resolved
  against the directory (RFC 3986 5.2), so the query that shapes an index
  (`?sort=name`) and the fragment belong to the request for the listing and do
  not reach the entries; `directory / "f.txt"` keeps them. A `str`
  destination of `rename()`, `copy()` and `move()` is another resource and
  takes neither (a signature in the query signs this resource only). To drop
  them from any path, `with_query(None)` and `with_fragment("")`.
- `stem` and `suffix` are those of `name` (the last segment of the decoded
  path; the query and the fragment are not part of it). `URILike` =
  `str | URI | os.PathLike`, what the constructor and the join accept.
- `str()`/`repr()` drop the password (`ftp://u:pw@h/p` → `ftp://u@h/p`);
  `as_uri(sanitize=False)` keeps it. Non-ASCII hosts render as IDNA. A
  query or fragment is printed as it is: a token carried there shows in
  `str()`/`repr()`.
- Authority: the first unescaped `:` of the userinfo separates user from
  password (`us%3Aer:pw` is the user `us:er`); a host of digits only
  (`http://20240101/key`) is the host; a port is 0-65535 (`URISyntaxError`
  otherwise, as for a `:` followed by anything but digits); an IPv6 zone is
  written `[fe80::1%25eth0]` (a bare `%` is read too). A name that holds a
  lone surrogate (a Windows file name can) renders as its UTF-8 bytes, so
  `str()`, `hash()` and `==` work on it.
- A host keeps the spelling it was given: `source.host` and the text of the URI
  are `nasA` for `wss://root:pw@nasA:8443`, and only the scheme is
  lower-cased by the parser (an address is its own spelling: `[FE80::1]` is
  written `[fe80::1]`). Everything that compares hosts folds the case itself:
  `==`, `hash()` and ordering of URIs, `same_authority()`, `is_relative_to()`
  and `relative_to()`, backend sharing, `rename()`, the same-file decisions
  of `copy()` and `move()`, the origin that keeps `Authorization` through a
  redirect, the proxy rules, `is_local()` and the connection cache of `ftp:`.
  The path, the userinfo, the query and the fragment compare exactly.
- `==` compares the URI text (with the host name in lower case). The other operand is a `URI` or a `str`, which is
  parsed first and so compared by what it names, not by its spelling
  (`URI("http://h/a b") == "http://h/a%20b"`); text that is not a URI is not
  equal, and nothing else is (a non-URI `Pathname` included). `hash` is that of
  the URI text, so a `str` that is not already in canonical form is equal to
  the `URI` but hashes differently: key a `set` or `dict` by `URI`.
- An authority is written back as it was read. An empty one (`file:///x`, host
  `""`) and none (`file:/x`, host `None`) are different URIs with different
  text, and name the same endpoint for backend sharing.
- `__fspath__()` — the path for a `file:` URI on this machine (a named host
  on Windows is a UNC path) or for a scheme with `_host_filesystem_path =
  True` (a scheme whose path is meaningful on **its** host); otherwise
  `NotImplementedError`. `host_fspath()` — the latter only, never local.

### `URIPath`

```python
class URIPath(URI, Path):
    def __init__(
        self, *args, schemesmap=None, findclass=False, **kwargs,
    ): ...
    @classmethod
    def __init_subclass__(cls, replace=False, **kwargs): ...
    @classmethod
    def schemes(cls) -> tuple[str, ...]: ...
    @classmethod
    def scheme_class(cls, name) -> type[URIPath]: ...
    backend
    def with_backend(self, backend): ...
    def _initbackend(self): ...
    def _listdir(self) -> Iterator[str]: ...
    def _scandir(self) -> Iterator[Tuple[str, Optional[FileStat]]]: ...
    def _reduce_options(self) -> dict: ...
```

`URI` + `Path`. The bare class (or `findclass=True`)
returns the subclass registered for the scheme, or plain `URIPath` for an
unknown scheme (its I/O raises `NotImplementedError`). The keywords are
`schemesmap`, `findclass`, `backend=` (see `backend` below) and the ones the
scheme class names in `_OPTIONS`; any other is a `TypeError` naming it, so a
misspelt `backend=` is never read as "use the default". The class of a scheme
that another distribution implements and that is not installed takes any
keyword: they are that distribution's to name. Resolution: classes
already imported → built-in `uripath.schemes.*` module → entry point
in group `uripath.schemes`, and an entry point never takes a built-in
name. An explicit `schemesmap` is the only map consulted. It is an allow-list of classes for dispatch, not a sandbox:
the path keeps it and every class chosen after construction uses it -- a
join with a `URI`/`URIPath` argument, `with_source()`, a `copy()`/`move()`
`str` destination and the outer URI of a `zip:`/`tar:`/`archive:` path (a
scheme the map omits gives a plain `URIPath`, whose I/O raises
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
  registering none of the class's names; `class MyPath(URIPath,
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
  its module or loading its entry point first; `UnsupportedSchemeError` naming
  the registered schemes when there is none, and the `ImportError` of a
  built-in module that cannot be imported. Both are classmethods of the
  one registry, whichever class they are called on.
- `backend` — per-instance connection state from `_initbackend()` (base:
  `None`), built on first use. A derived path (`/`, `joinpath()`,
  `parent`, `parents`, `with_name()`, `with_suffix()`, `with_query()`,
  `relative_to()`, `URIPath(base, x)`, a `URI`/`PurePath` join) never
  builds one -- so it never imports an I/O library either -- and takes the
  backend its source path already holds, or none. Paths derived from one
  another on one endpoint share one slot for the backend they derive for
  themselves: the first of them to need one calls `_initbackend()` (under a
  lock, so two threads build one) and the rest then use that object, so 20
  children of a fresh root open one connection. A path built separately
  (`URIPath(url)` twice), one on another endpoint, the sourceless result of
  `relative_to()` and a path that holds a supplied backend are not in it.
  `with_backend(backend)` returns a copy using `backend`. A backend is only
  shared within one endpoint (scheme, userinfo, host, port): a join,
  `with_source()` or `URIPath(base, url)` onto another endpoint takes none
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

### `as_path` and `copy_stream` (`uripath`)

```python
def as_path(text: str) -> LocalPath | URIPath: ...
def copy_stream(
    source: str | os.PathLike | Path | BinaryIO,
    target: str | os.PathLike | Path | BinaryIO,
    *,
    exclusive: bool = False,
    chunk_size: int = 1048576,
) -> None: ...
```

`as_path(text)` reads text the way the `uripath` command reads an argument.
It is a `URIPath` when it starts with an RFC 3986 scheme and either holds
`://` or the scheme is one a class registers (`data:`, `zip:`, `file:`,
`sftp:`, ...); anything else is a `LocalPath`, so `C:/data` (a one-letter
scheme is a drive), `12:30.txt`, `notes:draft` and `./a:b` stay local. A
scheme another distribution provides gives a `URIPath` whose first I/O raises
the `ImportError` that names what to install. `TypeError` for what is not a
`str`. It reads and connects to nothing.

`copy_stream(source, target)` copies bytes, `chunk_size` at a time, without
holding the object in memory. Each end is a binary stream (anything with
`read()` or `write()`), a path object, or text for `as_path()`; no text is
special, so `"-"` names a file called `-`. A path is opened and closed
inside the call; a stream stays open and is the caller's, and a target
stream is flushed at the end. `exclusive=True` opens a target path with an
exclusive create and raises `FileExistsError` for an existing one (no
check-then-write race); it means nothing for a target stream. A target
stream whose reader went away (a pipe whose other end closed; Windows reports
`OSError(EINVAL)`) raises `OutputClosedError`, which is also a
`BrokenPipeError`; the same error from a path's own connection is not
translated.

## Sources (`uripath.source`)

```python
class Source(NamedTuple):
    def __init__(self, scheme, userinfo, host, port): ...
    def reveal(self) -> str: ...
    @classmethod
    def parse(cls, text, *, strict=True) -> Source: ...
    @classmethod
    def try_parse(cls, text, default=None, *, strict=True) -> Source | None: ...
    def keys(self): ...
    def parsed_userinfo(self) -> tuple[str, str]: ...
    def get_scheme_cls(self, schemesmap=None): ...
    def is_local(self) -> bool: ...
```

`NamedTuple`,
falsy when all fields are empty; indexes by position, slice or field name.
`host` keeps the spelling it was given (`Source.parse("http://NasA").host ==
"NasA"`), so two `Source`s compare as tuples, exactly: use `same_authority()`
to ask whether they name one endpoint.
`str(source)` is the canonical text: the composer `URI.as_uri()` uses (`file://`
for an empty host and `file:` for none; an invalid scheme or port is a
`ValueError`), without the
password; `repr()` redacts it too, and both drop the whole userinfo for
`repo:`/`github:`/`gitlab:` (the fields keep it). `reveal()` is the text with
the password, as `URI.as_uri(sanitize=False)` is for a URI; it is named as an
action because its result carries the secret. `Source.parse(text, *,
strict=True)` reads the authority as `URI` does (`URISyntaxError` for a
path/query/fragment when strict, naming the component and never the text;
`TypeError` for what is not a `str`); `Source.try_parse(text, default=None, *,
strict=True)` returns `default` for text that does not parse and still raises
`TypeError` for what is not text. `parse(str(source))` is `source` except for
the password,
`parsed_userinfo() -> (user, password)` (`""` when absent; `userinfo`
stays the decoded `user:password` text),
`get_scheme_cls(schemesmap=None) -> type[URIPath]`, `keys()` (the field
names, so `dict(source)` works), `is_local()` —
`localhost`/empty host or an address of this machine (IP literal, or any
A/AAAA answer via `netimps`); the answer depends on the host alone and is
kept for 60 seconds for at most 256 hosts, so a miss does DNS.

## Queries (`uripath.query`)

```python
class Query:
    ENCODING = "utf-8"
    SEPARATOR = "&"
    def __init__(self, pairs=(), *, separator=None, encoding=None): ...
    @classmethod
    def parse(cls, text, *, separator="&", encoding="utf-8") -> Query: ...
    separator: str
    encoding: str
    def to_pairs(self) -> list[tuple[str, str | None]]: ...
    def to_dict(self, *, single=False): ...
```

An immutable value: the percent-encoded text and the pairs it stands for; it
is not a `str` and has no length, items or iteration (`len(query)` and
`for pair in query` are `TypeError`), and `isinstance(query, str)` is False.

- `Query.parse(text)` — any `str` parses, and is kept byte for byte: this is
  what `URI.query` holds, as received, and what is sent. `TypeError` for what
  is not a `str`. `Query(text)` is a `TypeError` pointing at `parse()`.
- `Query(pairs)` — from a mapping (a sequence value repeats the name) or from
  `(name, value)` pairs (`None` is a bare name), encoded so that `to_pairs()`
  returns what was given: `+`, `=`, the separator, `#`, `%` and white space
  are escaped (`{"sig": "ab+cd=="}` is `sig=ab%2Bcd%3D%3D`). `Query(query)`
  keeps the separator and encoding of the query it wraps unless they are given.
- `str(query)` is the text; `repr(query)` is `Query.parse('a=1')`, with
  `separator=` and `encoding=` when they are not the defaults; `bool(query)` is
  False for empty text.
- `to_pairs()` — the decoded pairs, in order. `to_dict(*, single=False)` —
  each name to the list of its values, or with `single` to its last. Decoding
  follows RFC 3986, not form-urlencoding: only `%XX` escapes are decoded and a
  `+` stays a plus (`urllib.parse.parse_qsl` reads form text); an escape that is
  not valid in `encoding` becomes a surrogate escape (`ERRORS`) and never
  raises.
- Equality and `hash()` are those of the decoded pairs, so `a=%41` equals
  `a=A`, and the separator decides the pairs: `a=1;b=2` is two pairs with
  `separator=";"` and one with `&`. A query is equal to nothing that is not a
  query (a `str` included).
- `Query.parse(str(query), separator=query.separator, encoding=query.encoding)
  == query`. Copies and pickles keep the separator and encoding.
- `QueryLike` = `str | Query | Mapping | Sequence[tuple[str, str | None]]` is
  what `URI.with_query()` accepts: text (taken as already percent-encoded), a
  mapping, pairs, or a `Query`; `None` removes the query.

## Built-in schemes (`uripath.schemes`)

Every class is dispatched by `URIPath(...)`; `uripath.schemes`
re-exports `FileURIPath`, `DataURIPath`, `HTTPURIPath`, `DAVURIPath`, `FTPURIPath`,
`ZipURIPath` and `TarURIPath` lazily. Backends are passed
as `URIPath(uri, backend=...)` or `path.with_backend(...)`.

### `FileURIPath` — `file:` (`uripath.schemes`)

```python
class FileURIPath(URIPath):
    filepath
```

`file:///abs`, `file:/abs`, `file:rel`,
`file://localhost/C:/x`. A path built from a local path object writes the
empty authority, as `pathlib.Path.as_uri()` does (`file:///C:/Windows/win.ini`,
`file:///etc/passwd`; the characters `!$&'()*+,;=:@` stay literal in the path
where `pathlib` escapes them, and both spellings read back as the same file);
a relative one has none (`file:rel/x`). `filepath -> LocalPath`; all I/O delegates to it
(listing reuses `LocalPath`'s scandir). `rename()` accepts local targets
only and returns a `FileURIPath`. No `symlink_to()`/`readlink()`. On Windows a
drive is the anchor: `parents` ends at the drive root (`file:///C:/`) and
equals the repeated `parent`, dot segments never climb above it, and a
`str` join key or `copy()`/`move()`/`rename()` destination reads `\` as a
separator (`C:\Temp\x` is an absolute path). A path with a named host is a
UNC path there, whose anchor is the share: `file://server/share/a/b` has the
ancestors `file://server/share/a` and `file://server/share/`, and the share
root is its own parent. A `FileURIPath` argument holding a drive
(`base / URIPath("file:///D:/f")`) restarts the join, as a `str` key does.
Elsewhere a backslash is a filename character and the root of a host is the
end of the chain, and every other scheme splits on `/` only.

### `DataURIPath` — `data:` (`uripath.schemes`)

```python
class DataURIPath(URIPath):
    mediatype: str
    charset: str
```

RFC 2397
`data:[<mediatype>][;base64],<data>`. `mediatype` property (default
`text/plain;charset=US-ASCII`). RFC 2397 has no query: an unescaped `?` and
what follows it are payload (`data:,a?b` reads `a?b`), while a `#` starts the
fragment. Read-only single file: `open("r")` only,
`stat().st_size` is the decoded size, listing → `NotADirectoryError`.
`charset` is the `charset=` the media type declares (quotes removed), `"utf-8"`
when it declares none; `open()` in text mode and `read_text()` decode with it
unless `encoding=` is given. The path is the payload, not a hierarchy: `name`,
`stem`, `suffix`, `suffixes`, `parent`, `parents`, `segments`, `with_name()`,
`with_stem()`, `with_suffix()`, `with_segments()`, `/`, `joinpath()`,
`relative_to()`, `is_relative_to()` and `match()`, and a constructor given
more than one part, raise `NotImplementedError` instead of cutting the
payload at a `/` (that would name another file). `with_path()`,
`with_query()` and `with_fragment()` replace a component as asked.

### `HTTPURIPath` — `http:`, `https:` (`uripath.schemes`)

```python
class HTTPURIPath(URIPath):
    def with_transport(
        self, transport, *, headers=None, timeout=(10, 60),
        write_method="PUT", append_mode="rewrite",
    ): ...
    def with_session(
        self, session, write_method="PUT", append_mode="rewrite",
        **requests_args,
    ): ...
    def stat(self, *, follow_symlinks=True, walk_up_last_modified=False): ...

class HTTPBackend:
    def __init__(
        self, transport=None, *, headers=None, timeout=(10, 60),
        write_method="PUT", append_mode="rewrite",
    ): ...
    def request(
        self, method, uri, *, data=None, headers=None, stream=False,
        allow_redirects=None, timeout=...,
    ): ...
    def close(self): ...

class HTTPWriteStream(BytesIO):
    def discard(self) -> None: ...
class HTTPAppendStream(BytesIO):
    def discard(self) -> None: ...

```

HTTP needs no library: a path sends through a **transport**, by default the
built-in `HTTPTransport` on `http.client`. The transport contract, `HTTPResponse`,
`HTTPTransport` (TLS, connection reuse, the `proxies=` provider), the rules for
redirects and for `Authorization`, the cap on a reply read whole
(`pathlib_next.http.MAX_REPLY_BYTES`) and the way a failed request becomes an
`OSError` are those of `pathlib_next.http`, documented in the `pathlib-next`
header under "HTTP requests". This section is what the paths add.

- **Choosing the transport.** `path.with_transport(transport, headers=None,
  timeout=(10, 60), write_method="PUT", append_mode="rewrite")` installs a
  backend over any transport (any object with `send()` and `close()` as that
  contract says; the caller closes it). `path.with_session(session,
  write_method="PUT", append_mode="rewrite", **requests_args)` is the same over
  a `requests.Session` (`None` makes a new one): `headers` and `timeout` in
  `requests_args` are the backend's, the rest go to the `requests` transport,
  which the distribution `pathlib-next-requests` provides. Without that
  distribution the call raises `ImportError` naming it. Without either, a
  path's backend builds the built-in transport on first use (`HTTPBackend.close()`
  or leaving its `with` block closes a transport the backend built); the
  environment variable `PATHLIB_NEXT_HTTP_TRANSPORT` (`builtin`, or the name of an
  installed transport) names that default for the process.
  `HTTPBackend(transport=None, *, headers=None, timeout, write_method,
  append_mode)` is the backend a path holds: a `pathlib_next.http.HTTPClient`
  whose `request()` takes a path or a URL.
- **What the backend does for every transport.** It follows redirects, adds
  credentials and default headers (`User-Agent: uripath/<version>`, `Accept:
  */*`), applies the default timeout `(10, 60)` seconds (`timeout=None` waits
  forever), and the path maps a status to a pathlib exception. `headers` given
  to the backend go with every request; request-specific headers merge over them
  by name (case-blind). A header value or URL with a control character (CR and
  LF included) is `ValueError`, before anything is sent. A reply it needs whole
  (a PROPFIND's, a git API's JSON, `request(stream=False)`'s) may be at most
  `pathlib_next.http.MAX_REPLY_BYTES` after decoding, however small it is on the
  wire: more is `OSError(EFBIG)` naming the path, and the connection is closed.
  A reply whose body nobody looks at (a write's, a DELETE's, an error's) is read
  up to that many bytes and dropped, so its connection can be reused when the
  body was short. The content of a file (`open("r")`, a git file) is not limited.
- Redirects: the rules are `pathlib_next.http`'s (`GET`/`HEAD`/`OPTIONS` follow
  up to 30; a redirect that changes the scheme, host or port drops
  `Authorization`; every other request is sent again once after a 307/308, for
  `PROPFIND` also a 301, 302 or 303, to the same origin, and is otherwise
  `OSError(EIO)`). A path asks again after a redirect where it needs the final
  answer, `stat()`, `exists()`, `is_dir()`, `unlink()`, `open("x")` and a
  patch-mode append included, and none of those sends `Authorization` to the
  other origin. Headers other than `Authorization` from
  `with_transport(headers=...)` (`X-Api-Key`, a vendor token header, a cookie)
  are sent to the new host as well, even to a plain `http:` one, so keep a
  secret in `Authorization`, or point the path at the final URL.
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
  one over `pathlib_next.http.MAX_REPLY_BYTES` (8 MiB after decoding; assign a
  larger number to allow more) is `OSError(EFBIG)`. A name that is not
  UTF-8 (`caf%E9`) keeps its bytes (`surrogateescape`) and is requested as
  listed. A listed child carries neither the query nor the fragment of the
  directory's URL (the query is addressed to the listing; see "Query and
  fragment" under `URI`).
- `open("r")` streams `GET` with `Accept-Encoding: identity`; the mode is
  matched exactly, so `"r+"`, `"w+"` and `"a+"` raise `NotImplementedError`.
  `"w"`/`"x"` (an `HTTPWriteStream`)
  buffer and send `write_method` on close. `"x"` first calls `stat()`: found
  → `FileExistsError`, a failure other than not-found raises with nothing
  sent; the upload then carries `If-None-Match: *`, and a 412 reply →
  `FileExistsError` (a server that ignores the header leaves the window
  between probe and upload open). `"a"` (an `HTTPAppendStream`):
  `append_mode="rewrite"` (GET + full
  re-upload, not atomic) or `"patch"` (`PATCH` with `Content-Range` from the
  `HEAD` size; a `HEAD` reply without `Content-Length` → `OSError(EIO)`
  naming the path, nothing sent; a refusal raises `PermissionError` for
  401/403/405/501, `OSError(EIO)` for other statuses). An `open("a")` that
  raises (the read of the current content, or the `HEAD` of patch mode,
  failed) has uploaded nothing. A `with` block that ends in an exception (any
  `BaseException`) sends nothing, in binary and in text mode: the stream is
  discarded before it is closed (`discard()`, from
  `pathlib_next.providers.DiscardOnError`), so the file keeps its content or
  is not created. A stream closed with `close()`, or by a block that ended
  normally, sends once.
- `unlink()` sends `DELETE` and refuses a directory (`IsADirectoryError`,
  judged by `stat()`); `rmdir()` requires an empty directory. No `mkdir()`,
  `rename()`, `chmod()`.
- Status mapping: 404/410 → `FileNotFoundError`, 401/403/405/501 →
  `PermissionError`, 409 → `FileExistsError` (`FileNotFoundError` for
  writes), other → `OSError(EIO)` with the status. A transport's
  `TimeoutError` and `ConnectionError` are re-raised naming the path, with
  no cause. Text that came from the server and goes into a message (a reason
  phrase, a `Location`, a rate-limit header, the `href` of a failed `DAVURIPath`
  member) is shown with control, line-separator and bidirectional characters
  escaped (`\x1b` for ESC) and cut to 120 characters (200 for a URL).

### `DAVURIPath` — `dav:`, `davs:` (`uripath.schemes`)

```python
class DAVURIPath(HTTPURIPath):
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
`HTTPURIPath`, probing with `PROPFIND`); `"a"` unsupported, so `append_mode`
has no effect. `mkdir()` = `MKCOL`
(missing parent → `FileNotFoundError`). `unlink()` refuses a collection;
`rmdir()` checks emptiness first; `rm(recursive=True)` is one recursive
`DELETE` (failed members of a 207 raise). `rename()` = `MOVE` with
`Overwrite: F` (existing target → `FileExistsError`), no credentials in
`Destination`, which carries the target's own query (never the source's)
and no fragment. 423 → `PermissionError`. `PROPFIND`, `PUT`, `MKCOL`, `DELETE`
and `MOVE` follow the `HTTPURIPath` redirect rule above (a listing is scoped to
the URL that answered it). No `chmod()`.

### `FTPURIPath` — `ftp:`, `ftps:` (`uripath.schemes`)

```python
class FTPURIBackend(BaseFTPURIBackend):
    timeout
    ssl_context
    verify
    def __init__(
        self, timeout=30.0, ssl_context=None, verify=True,
    ) -> None: ...

class BaseFTPURIBackend:
    def client(self, source, tls) -> _ftplib.FTP: ...
    def close(self) -> None: ...
```

- `FTPURIBackend` — `timeout`
  bounds connect, replies and transfers (`None` = forever). `ftps:` is
  explicit TLS with `PROT P`; the certificate and host name are verified
  with `ssl.create_default_context()`; `ssl_context` (e.g.
  `ssl.create_default_context(cafile=...)`) wins over `verify`;
  `verify=False` accepts any certificate (and logs a warning on the
  `uripath` logger each time one is built). Data connections reuse the TLS
  session. No user in the URI → anonymous login.
- `BaseFTPURIBackend.client()` — override to supply
  connections. `close()` closes every connection the paths of the backend hold,
  whichever thread opened it (one a command is running on closes when the
  command ends), may be called twice, and a later use connects afresh; the
  backend is a context manager that calls it. One backend may be shared
  between threads, each of which keeps its own connection per server. These two classes are not `pathlib_next.ftp.FTPBackend` and
  `BaseFTPBackend`: those belong to one host, these connect to the `Source` of
  whichever path asks.
- Paths without `backend=` share one default `FTPURIBackend()`. Connections
  are cached per (backend, source, tls, thread) (LRU of 128, closed on
  eviction, and closed when their thread ends). A connection that carried
  a command within the last `pathlib_next.ftp.IDLE_PROBE_SECONDS` (1 second) is used as it is; one idle for longer, or not
  yet used, is probed with `NOOP` and replaced when dead.
- `FTPURIPath` is a `URIPath` over `pathlib_next.ftp.FTPPath`: the listing,
  stat, reads, writes, `rename()`, `chmod()` and `_utime()` are those
  described under "What a path does" in the FTP section of the `pathlib-next`
  header, and an `OSError` names the URI. A `with` block over `open("w")` that raised uploads nothing.
  Its URI-only parts are the endpoint (the `Source` and the
  scheme's `tls`) and the backend rules above.
- An empty path (`ftp://host`) is the root, as `ftp://host/` is: `/` is
  sent in every command that takes a path, never an empty argument (which a
  server reads as its working directory).

### Archives — `zip:`, `tar:`, `archive:` (`uripath.schemes`)

```python
MEMBER_SPOOL_BYTES = 16777216

class ArchiveURIPath(URIPath):
    def refresh(self) -> None: ...
    def batch(self) -> ContextManager[None]: ...
    def readlink(self) -> LinkTarget: ...
class ZipURIPath(ArchiveURIPath): ...
class TarURIPath(ArchiveURIPath): ...
ArchiveZipURIPath = ZipURIPath
ArchiveTarURIPath = TarURIPath
```

`ZipURIPath` (`zip:`), `TarURIPath` (`tar:`),
`ArchiveURIPath` (`archive:`, detects the format from the outer name
`.zip`/`.jar` vs `.tar`/`.tgz`/`.tar.*`, else a `PK` magic sniff),
`ArchiveZipURIPath` (`archive+zip:`), `ArchiveTarURIPath` (`archive+tar:`). The last
two are second scheme names of `ZipURIPath` and `TarURIPath`, and the class names
are aliases of those (`ArchiveZipURIPath is ZipURIPath`); a path prints and pickles
with the scheme it was written with.

- `archive:` settles the format on first use, not when the path is built:
  constructing, printing, joining, copying and pickling a path read nothing,
  a non-local outer that had to be read to decide is not fetched a second
  time, and a failure to read the outer propagates and decides nothing, so
  the next call tries again.
- Syntax `<scheme>:<archive-uri>!/<member>`; `<archive-uri>` must carry a
  scheme (`URISyntaxError` otherwise) and may be any URI, including another
  archive (each leading archive scheme consumes one `!/`; nested archives
  are read-only). A member name containing `!/` is written `%21/`.
  `name`/`parent`/`glob()` work on the member path; `as_uri()`
  percent-encodes it, and a name that is not valid UTF-8 (a tar member
  written in another charset, held as surrogate escapes) keeps its bytes as
  `%XX` (`caf%E9.txt`), so such a path prints, hashes, compares and parses
  back to the same member.
- One shared handle per archive (keyed by the real local path, or the outer
  URI), released when no path references it. `ArchiveURIPath.refresh()` forgets
  what is held of the outer, so the next use reads it again; the rest is
  described under `ArchivePath` in the `pathlib-next` header.
- `ArchiveURIPath` is a `URIPath` over `pathlib_next.archive.ArchivePath` (`ZipURIPath`
  over `ZipPath`, `TarURIPath` over `TarPath`) on the shared handle of its outer:
  member names, the archive root, links, cost, writes, `batch()`, the removal
  and the damage errors are those described under "Archives
  (`pathlib_next.archive`)" in the `pathlib-next` header, with an `OSError`
  naming the URI. A `with` block
  over `open("w")` that raised adds no member and creates no archive.
  `uripath.schemes.MEMBER_SPOOL_BYTES` is the same setting as
  `pathlib_next.archive.MEMBER_SPOOL_BYTES`.

## For scheme implementers (`uripath`, `uripath.schemes`, `uripath.source`)

The names a `URIPath` subclass overrides or calls beyond `URI` and `URIPath`
above, in one place: the built-in schemes use all of them, so they are
contract (the hooks of `pathlib_next.Path` they also use are listed under "For
path implementers" in the `pathlib-next` header). Each helper also keeps an
underscore spelling that is the same object (`_same_authority`,
`_DerivedBackend`, `_compose_uri`, `_compose_host`, `_encode`, `_is_drive`,
`_SAFE_PATH`, `_ERRORS`).

```python
class URI(Pathname):
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
    def _join_decoded(self, key) -> URI: ...
    def _is_absolute_decoded(self, path) -> bool: ...
    def _rename_target(self, target) -> URI: ...
    def _same_location(self, other) -> bool: ...
    def _identity(self) -> str: ...
    _initiated
    _raw_uris
    _source
    _query
    _OPTIONS

class URIPath(URI, Path):
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

class DelegatingURIPath(URIPath):
    _DELEGATED: Sequence[str]
    _RELABEL: bool
    def _make_core(self) -> Path: ...
    def _delegated(self, *extra) -> ContextManager[None]: ...
    def _supports(self, protocol) -> bool | None: ...
    _core_path

def same_authority(a, b) -> bool: ...
class DerivedBackend: ...
```

```python
# uripath.source
def compose_uri(scheme, userinfo, host, port, path, query, fragment) -> str: ...
def compose_host(host) -> str: ...
def fold_host(host): ...
def percent_encode(text, safe) -> str: ...
def is_drive(segment) -> bool: ...
SAFE_PATH = "!$&'()*+,;=:@/"
ERRORS = "surrogateescape"
```

Building and deriving a path:

- `_init(source, path, query, fragment, **kwargs)` — stores the decoded
  components; every constructor, join and `with_*()` ends here, and it may run
  again on a live instance. An override sets its own state, then calls
  `super()._init()`. `URIPath._init` also takes `backend=`, a backend the
  caller supplied.
- `_from_parsed_parts(source, path, query, fragment, /, **kwargs)` — a
  same-type instance from decoded components with no parsing (a `rename()`
  result, a probe); the keywords reach `_init()`.
- `_format_parsed_parts(source, path, query, fragment, /, sanitize=True)`
  — the URI text of decoded components (`sanitize` drops the password);
  `as_uri()` and `str()` call it, so a scheme with a different spelling
  overrides it. `_parse_uri(uri)` is its reverse for URI text: `(Source,
  decoded path, Query, fragment)`.
- `_OPTIONS` — the names of the keyword arguments the constructor takes: a
  `frozenset`, `{"backend", "schemesmap", "findclass"}` on `URIPath`, empty on
  `URI`, and `None` for any. A scheme whose class reads keywords of its own
  (`ssh_config=`, say) extends it (`_OPTIONS = URIPath._OPTIONS | {"ssh_config"}`)
  and returns them from `_reduce_options()`; any name not listed is a
  `TypeError` at construction, before the path is built.
- `_load_parts()` — parses a path that was built from arguments and is not
  parsed yet; `source`, `path`, `query` and `fragment` call it. Call it
  before reading `_source`, `_query` or the backend state of a path that may
  still be waiting (`_initiated` is False; `_raw_uris` holds its arguments).
- `_make_child_relpath(name, stat_hint=None, **kwargs)` — the child called
  exactly `name` (one segment, never re-parsed), with the query and fragment
  of this path; `iterdir()`, `_scandir()` and the `str` join build children
  with it, so a scheme that gives a name a meaning (a `-`, say) overrides
  it. `stat_hint` is the listing's stat for that child; `http:` and `dav:`
  build a listed child without the query and fragment (see "Query and
  fragment").
- `_join_decoded(key)` — joins an already-decoded path string name by name
  through `_make_child_relpath()`, dot segments resolved as RFC 3986 5.2.4
  says; an absolute key restarts at the root of the same source.
  `_is_absolute_decoded(path)` says whether a string restarts a join (a leading
  `/`; `FileURIPath` also a drive path).
- `_identity()` — the text `==`, `hash()` and ordering compare: `as_uri()` with
  the host name in lower case. Key a cache on it, not on `as_uri()`, when two
  spellings of a host must share an entry.
- `_rename_target(target)` — a `rename()` destination as a `URI`: a `str` is a
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
  `http:` (an index without exact sizes) does.
- `_listdir()` — the names `_scandir()` lists by default; a stub. `iterdir()` and
  the default `_scandir()` are built on it (`providers.derived_from`), so
  `pathlib_next.protocols.supports(cls, Listing)` is true for a scheme that defines
  `_listdir()` or its own `_scandir()` and false for one that does neither
  (`data:`).
- `_schemes()` — the scheme names this class registers.

A stream that commits when it is closed (an upload, a rewrite of an archive)
inherits `pathlib_next.providers.DiscardOnError`, first in its bases, and defines
`discard()`: a `with` block over the file that raised then commits nothing (the
contract is in the `pathlib-next` header, "For path implementers"). The
`HTTPWriteStream` and `HTTPAppendStream` of `http:` and `dav:` are such streams;
a stream that writes through as it goes needs none.

Backend state (read it only in an override that changes how a path carries a
backend, as the archives do):

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

Delegating to a path that needs no URI (`uripath.schemes.DelegatingURIPath`,
the base of `file:`, `ftp:` and the archive schemes, and of `sftp:` in the
distribution that provides it):

- `_make_core()` — the `pathlib_next.Path` this URI names, built from `source`
  and `path` and performing no I/O; it is made once per instance and is the
  `_core_path`. A scheme names the hooks it hands to it in `_DELEGATED`: any of
  `_scandir`, `_listdir`, `_open`, `_mkdir`, `unlink`, `rmdir`, `chmod`,
  `_chown`, `_utime`, `_symlink_to`, `readlink`, `_write_batch`,
  `_same_filesystem` and `_node_key`; each calls the core path's method of the
  same name, and a hook not named stays what `URIPath` defines. `stat()` takes
  the listing's hint (see `_pop_stat_hint()`) before it asks the core path.
- `_supports(protocol)` — what `protocols.supports()` asks an instance: the
  core path's answer for a protocol this class has a hook for, so a scheme that
  hands over `_utime` to a core path that cannot set times says no; `None` for a
  protocol the class does not implement at all.
- `_delegated(*extra)` — a context manager for the call of a core path that a
  scheme writes by hand (`rename()`, `copy()`): an `OSError` that names the core
  path, or a pair of `extra` `(core text, this text)`, names this path instead.
  `_RELABEL = False` turns that off for a core path that is itself the user's
  file (`file:`).
- The URI layer keeps everything about URIs: parsing, joining, the backend and
  how paths of one endpoint share it, the text of the path and the keywords of
  the constructor (`_OPTIONS`). The protocol, its errors and its caches belong to
  the core path.

Composing text:

- `compose_uri(scheme, userinfo, host, port, path, query, fragment)` — URI text
  from decoded components, each percent-encoded for its part; `None` omits one
  and an invalid scheme, port or path/authority pairing is a `ValueError`.
  `compose_host(host)` encodes a host (an IPv6 address is bracketed, an
  internationalized name is IDNA) and keeps the case of a name.
  `fold_host(host)` is the host as a comparison or a key reads it: a name in
  lower case, an address or `None` as it is. A scheme that keeps something per
  server (a connection, a cache) keys it on `fold_host(source.host)`, or on
  `same_authority()` of two sources. `percent_encode(text, safe)` encodes UTF-8
  and keeps the characters of `safe`; `SAFE_PATH` is the set a path keeps.
  `ERRORS` is the error handler for percent-decoding and re-encoding
  (`"surrogateescape"`: a byte that is not UTF-8 survives the round trip).
- `is_drive(segment)` — whether a segment is a Windows drive (`"C:"`).

## Provided by other distributions

`uripath` knows these schemes and this transport by name and does not contain
them:

| Name | Distribution | Install |
| --- | --- | --- |
| `sftp:` | `sftppath` | `pip install "sftppath[paramiko]"` (or `[asyncssh]`) |
| `s3:`, `gs:`, `az:` | `objpath` | `pip install "objpath[s3]"` (or `[gs]`, `[az]`) |
| `repo:`, `github:`, `gitlab:` | `repopath` | `pip install repopath` |
| the `requests` HTTP transport | `pathlib-next-requests` | `pip install pathlib-next-requests` |

A path of one of the schemes builds, joins, compares and prints without its
distribution, and is listed by `URIPath.schemes()`. Every operation that needs
the server (`stat()`, `exists()`, `open()`, `iterdir()`, a write, `rename()`,
`chmod()`, ...) raises `ImportError`, with a message that names the scheme and
the install command and never the URI (it can carry a password). So does
`URIPath.scheme_class(name)`. The installed distribution registers its own
class for the name, through an entry point of the group `uripath.schemes`, and
that class is used; its constructor takes the keywords that its `_OPTIONS`
names. An entry point never takes a built-in scheme over: `file`, `http` and
the other names `URIPath.schemes()` lists as built in keep their classes, and
a class that names one without `replace=True` is a `ValueError` where it is
defined.

For the `requests` transport, `HTTPURIPath.with_session()` and
`PATHLIB_NEXT_HTTP_TRANSPORT=requests` use the class that the installed
`pathlib-next-requests` declares in the group `pathlib_next.http_transports`,
and raise `ImportError` naming it when it is not installed.

## Exceptions

### `uripath.exceptions`

```python
class URIPathError(Exception): ...
class URISyntaxError(URIPathError, ValueError): ...
class UnsupportedSchemeError(URIPathError, ValueError): ...
class OutputClosedError(URIPathError, BrokenPipeError): ...
```

`URIPathError` is the base of what goes wrong at run time; the root `uripath`
exports it and the two below.

- `URISyntaxError` — text that is not a URI, or not the part of one that was
  asked for: a port that is not 0-65535, a malformed host or IPv6 address, a
  `zip:` URI without the scheme of its archive, `Source.parse()` of text with a
  path. The message names the
  fault and never the text, which can carry a password.
- `UnsupportedSchemeError` — `URIPath.scheme_class(name)` for a scheme nobody
  registered; the message lists the registered ones.
- `OutputClosedError` — `copy_stream()` found that the reader of its target
  stream went away; only `uripath.exceptions` exports it.

A caller's bad argument stays a plain `ValueError` or `TypeError`: a name
another class holds (`ValueError` at the class statement), a path outside its
base (`relative_to()`), an object that is no path. Unsupported operations
raise `NotImplementedError`. Network errors map to pathlib types
(`FileNotFoundError`, `PermissionError`, `FileExistsError`,
`IsADirectoryError`, `NotADirectoryError`, `OSError(ENOTEMPTY)`), timeouts to
`TimeoutError`, anything else to `OSError`; transport exceptions are not
chained (their text can carry credentials).

## Command line

### `uripath.cli` (`pip install "uripath[cli]"`)

```python
def main(argv: Sequence[str] | None = None) -> int: ...
```

The `uripath` console script is `uripath.cli:main`, and `python -m uripath` runs
the same function. It is built on `duho` and needs the `cli` extra; `import
uripath` never imports `uripath.cli` or `duho`, and `uripath.cli` is not library
API (it is absent from the root `__all__`): its one public name is `main`. Without `duho`, `main()`
prints `pip install "uripath[cli]"` to stderr and returns 1. `main()` returns
the exit status and never raises `SystemExit`; it reads and writes the
process's standard streams (binary through `sys.stdin.buffer` and
`sys.stdout.buffer`).

Each command is a `duho` command class in `uripath.cli.<name>`; the root,
`uripath.cli.Uripath`, is built on first use. Every command calls the library
(`as_path()`, `copy_stream()`, `Path.copy()`, `Path.rm()`, `PathSyncer`), so
nothing the command does is reachable only from it. A PATH is read by
`as_path()`: an argument with `://`, or with a scheme some class registers
(`data:`, `zip:`, ...), is a `URIPath`; everything else (including `C:/x` and
`notes:draft`) is a `LocalPath`. `-` is stdin/stdout where bytes are read or
written. `--` ends the options and takes no argument after it (a path that
starts with `-` is written `./-name`).

| Subcommand | Arguments and flags |
| --- | --- |
| `read PATH` | Copy `PATH`'s bytes to stdout in chunks. |
| `write PATH [DATA] [--encoding utf-8]` | Write `DATA` encoded, or stdin's bytes when omitted, replacing `PATH`. |
| `rm PATH [-r/--recursive] [--missing-ok] [--ignore-error]` | `Path.rm()`; a directory with content needs `--recursive`. |
| `cp SOURCE TARGET [-r/--recursive] [--overwrite] [--follow-symlinks/--no-follow-symlinks] [--preserve-metadata/--no-preserve-metadata]` | `Path.copy()`; with `-`, `copy_stream()` (an existing target needs `--overwrite`; no `-r`). |
| `sync SOURCE TARGET [--dry-run] [--remove-missing] [--size-only] [--follow-symlinks/--no-follow-symlinks] [--follow-mounts/--no-follow-mounts]` | `PathSyncer` with content comparison; `--size-only` compares sizes; nothing is deleted without `--remove-missing`. `--dry-run` prints `would copy SRC -> DST`/`would remove`/`would mkdir`/`would replace`/`would symlink`; `-v` prints the changes made. `--no-follow-mounts` fails (exit 1, `OSError(EXDEV)`) on a mount point inside TARGET instead of syncing into it. |

Every command takes `-v`, `-q` and `--loglevel` (the `uripath` logger, on
stderr). Results go to stdout, diagnostics to stderr, and no message carries a
password or a token.

Exit status: 0 success (also `--help` and `--version`); 1 the operation failed,
with one line `uripath: <Type>: <message>` on stderr, or the `cli` extra is
missing; 2 a wrong invocation, with the usage or the problem on stderr (a
missing or unknown argument, `cp -r` with `-`, an unknown `--encoding`); 130
Ctrl-C; 141 the reader of stdout went away, quietly (on Windows too, where a
closed pipe reports `EINVAL`).

Served as tools (`URIPATH_MCP=stdio uripath`) the five commands are the tools
`uripath.read`, `uripath.write`, `uripath.rm`, `uripath.cp` and `uripath.sync`,
with the schemas their fields give; `AGENT_HELP=1 uripath --help` prints one
JSON document for the tree. A tool has no standard input: `-` as a source, and
`write` without `DATA`, fail with a message. Every deleting or replacing
option is off unless it is passed.

## Environment variables

### `PATHLIB_NEXT_HTTP_TRANSPORT` (read by `pathlib_next.http`)

`builtin` (the default when unset), or the name of a transport an installed
distribution declares in the group `pathlib_next.http_transports` (`requests`,
from `pathlib-next-requests`): the transport that `http(s):` and `dav(s):`
build for a backend that was not given one. `requests`
without that distribution raises `ImportError` naming it. The value is
case-sensitive, and an empty or unrecognised one raises `ValueError` naming the
choices (`pathlib_next.http.transport_names()`). It is read when a backend first
needs its transport, once per backend, so a change reaches backends built
afterwards. `with_transport()` and `with_session()` do not read it.

### Proxy variables (URI layer)

`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY`, in upper or lower case:
`HTTPTransport` reads them, through `urllib.request`, when it is built with
`proxies=None`. A `proxies=` argument, `{}` included, is used instead and the
environment is not read.

### `URIPATH_MCP` and `AGENT_HELP` (command line)

`URIPATH_MCP=stdio` makes `uripath` serve its five commands as tools instead of
running one; `AGENT_HELP=1` makes `uripath --help` print one JSON document for
the command tree. `duho` reads both when the command starts; the library does
not.

## Gotchas

Importing `uripath` and constructing a path of any scheme does no I/O. A path
joins, compares and prints without touching a server; the first operation that
needs one (`exists()`, `stat()`, a read, a listing, `is_local()`) connects.
That holds for the schemes another distribution provides as well: without the
distribution their paths join, compare and print, and the first operation that
needs the server raises `ImportError`.
