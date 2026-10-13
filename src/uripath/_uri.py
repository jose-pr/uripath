from __future__ import annotations

import os
import pathlib as _pathlib
import posixpath as _posix
import typing as _ty

import uritools

if _ty.TYPE_CHECKING:
    from typing import TypeAlias
else:
    TypeAlias = _ty.Any

from pathlib_next import Path, Pathname
from pathlib_next.providers import name_stem as _name_stem
from pathlib_next.providers import name_suffix as _name_suffix
from .query import Query, QueryLike, _coerce
from .source import Source
from .source._compose import _encode
from .source._parse import _ERRORS, _is_drive, _remove_dot_segments
from .source._source import _parse_source, _same_authority, _source_parts
from .source._compose import _compose_uri

URILike: TypeAlias = "str | URI | os.PathLike"


_NOSOURCE = Source(None, None, None, None)
_NO_QUERY = Query.parse("")


def _segments_of(path: str) -> list[str]:
    """Split a normalized posix-style path into segments for prefix
    comparison. "/" alone must yield [""] (the root), not ["", ""]
    (str.split's artifact for a string ending in "/")."""
    if path == "/":
        return [""]
    return path.split("/")


def _uriencode(text: str, safe=""):
    return _encode(text, safe)


def _path_reference(posix: str) -> str:
    """Encode a posix path as a URI reference that parses back to the same
    path. A path starting with "//" (POSIX keeps exactly two leading
    slashes) would otherwise parse as a network-path reference whose first
    segment is a host; "/." in front of it is removed again as a dot
    segment (RFC 3986 5.2.4)."""
    encoded = _uriencode(posix, safe="/")
    return "/." + encoded if encoded.startswith("//") else encoded


class _RelativeLocalPath(str):
    """The encoded posix spelling of a *relative* concrete local path
    (`pathlib.Path("a/b")`, `LocalPath("a/b")`) in `URI._raw_uris`.

    It joins like a relative `PurePath` -- onto the preceding segments,
    keeping their source -- and supplies a `file:` scheme only when no
    segment has a source at all. Turning it into `file:a/b` up front let
    that scheme replace the base's, so
    `URIPath("sftp://h/srv/") / pathlib.Path("etc/x")` became the LOCAL
    file `/srv/etc/x`."""

    __slots__ = ()


_FILE_SOURCE = Source("file", None, "", None)


def _remove_dots(path: str, scheme: "str | None") -> str:
    """`_remove_dot_segments()`, keeping the drive of a `file:` path on
    Windows."""
    return _remove_dot_segments(path, drive=scheme == "file" and os.name == "nt")


def _segment_text(item) -> str:
    """The text of one `with_segments()` element."""
    if isinstance(item, str):
        return item
    if isinstance(item, bytes):
        return item.decode()
    if isinstance(item, (_pathlib.PurePath, Pathname)):
        return item.as_posix()
    path = os.fspath(item)
    if isinstance(path, bytes):
        path = path.decode()
    return _pathlib.PurePath(path).as_posix()


def _child_path(path: str, name: str, has_authority: bool) -> str:
    """The path of the child `name` of a directory at `path`: exactly one "/"
    joins them (a directory's own path conventionally carries a trailing "/"
    for some schemes, and "/" + "sub" must not become "//sub"). An empty path
    with an authority is the same root as "/" (RFC 3986: "http://host" and
    "http://host/" are equivalent); without one ("file:", "data:") it is
    relative and stays so."""
    if not path:
        return f"/{name}" if has_authority else name
    return (path if path.endswith("/") else f"{path}/") + name


def _empty_slashes(path: str, count: int, between: bool) -> int:
    """How many "/" spell `count` empty segments after `path`. With `between`
    a name follows, and `_child_path()` supplies the slash that precedes it
    only when `path` does not end in one."""
    return count - (1 if path.endswith("/") else 0) + (1 if between else 0)


def _slot_names(cls: type) -> "tuple[str, ...]":
    """Every slot a `cls` instance has, base classes included, each once."""
    names: "dict[str, None]" = {}
    for klass in cls.__mro__:
        slots = klass.__dict__.get("__slots__", ())
        for slot in (slots,) if isinstance(slots, str) else slots:
            if slot not in ("__dict__", "__weakref__"):
                names[slot] = None
    return tuple(names)


def _as_uri(value) -> "URI":
    """`value` as the constructor reads one argument: a `TypeError` for
    what it cannot read."""
    converted = URI.__new__(URI)
    converted.__init__(value)
    return converted


def _has_dot_segment(path: str) -> bool:
    # A "." or ".." segment starts with a dot right after a "/" or at the
    # start; a cheap superset test that decides whether to run the real one.
    return "/." in path or path.startswith(".")


class URI(Pathname):
    """A pure (no I/O) RFC 3986 URI, lazily parsed into `source` (scheme/
    userinfo/host/port), `path`, `query`, and `fragment` on first access.
    Join semantics (multiple constructor args, or `/`) are pathlib-
    `joinpath`-like, not RFC 3986 reference resolution -- see
    `_load_parts`'s docstring and `docs/divergences.md`."""

    __slots__ = (
        "_raw_uris",
        "_source",
        "_path",
        "_query",
        "_fragment",
        "_uri",
        "_initiated",
        "_normalized_path",
        "_segments_cache",
        "_suffix_cache",
        "_stem_cache",
    )

    #: `True` on a subclass whose `.path` is a filesystem path on the URI's own host
    #: (`sftp:`): `__fspath__`/`host_fspath()` return it for a command line that
    #: runs on that host. `False`: `.path` has no such meaning (`http:`, `s3:`).
    _host_filesystem_path = False

    #: Every slot of the class, set by `__init_subclass__`; `__new__` starts
    #: each one at None so `__init__` can tell an initialized instance.
    _slot_names: "tuple[str, ...]" = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._slot_names = _slot_names(cls)

    def __new__(cls, *uris, **options):
        inst = object.__new__(cls)
        for slot in cls._slot_names:
            setattr(inst, slot, None)
        return inst

    def __init__(self, *uris: URILike, **options):
        if self._raw_uris or self._initiated:
            return
        _uris: list[str | URI] = []
        for uri in uris:
            if uri is None or (isinstance(uri, (str, bytes)) and not uri):
                uri = ""
            if isinstance(uri, URI):
                _uris.append(uri)
            elif isinstance(uri, (_pathlib.Path, Path)):
                try:
                    uri = uri.as_uri()
                except ValueError:
                    # as_uri() raises ValueError for a relative path, which
                    # joins like a relative PurePath (see _RelativeLocalPath).
                    uri = _RelativeLocalPath(_uriencode(uri.as_posix(), safe="/"))
                _uris.append(uri)
            elif isinstance(uri, (_pathlib.PurePath, Pathname)):
                _uris.append(_path_reference(uri.as_posix()))
            elif hasattr(uri, "as_uri"):
                path = uri.as_uri
                if callable(path):
                    path = path()
                _uris.append(path)
            elif isinstance(uri, str):
                _uris.append(uri)
            elif isinstance(uri, bytes):
                _uris.append(uri.decode())
            else:
                path = None
                try:
                    path = os.fspath(uri)
                except (TypeError, NotImplementedError):
                    pass
                if not isinstance(path, str):
                    raise TypeError(
                        "argument should be a str or an os.PathLike "
                        "object where __fspath__ returns a str, "
                        f"not {type(uri).__name__!r}"
                    )
                # Only __fspath__ is guaranteed here -- posix-normalize the
                # string itself rather than assuming an as_posix() method.
                posix = _pathlib.PurePath(path).as_posix()
                _uris.append(_path_reference(posix))
        self._raw_uris = _uris

    @classmethod
    def _parse_uri(cls, uri: str) -> tuple[Source, str, Query, str]:
        """`(source, path, query, fragment)` of `uri`, in one pass over
        `urisplit()`'s raw fields with the authority split once. It differs
        from uritools' getters in three ways: the query is not decoded (`.query`
        stays percent-encoded and is decoded per key and value by
        `Query.to_pairs()`, because decoding it makes an escaped `&`, `=` or `+`
        look like a delimiter); escapes that are not UTF-8 decode with
        `surrogateescape` (`source._ERRORS`) instead of raising; and a `data:`
        payload (RFC 2397) is an opaque octet string that gets no dot-segment
        removal (`data:,a/./b` is the bytes `a/./b`)."""
        # One pass over `urisplit()`'s raw fields, authority split once; where this
        # differs from uritools' getters is in the docstring.
        scheme, authority, path, query, fragment = uritools.urisplit(uri)
        scheme = scheme.lower() if scheme is not None else None
        source = _parse_source(scheme, authority)
        if scheme != "data":
            path = _remove_dots(path, scheme)
        decoded = uritools.uridecode(path, errors=_ERRORS)
        if decoded != path and scheme != "data":
            # An escaped dot (`%2e%2e`) or separator (`..%2Fx`) is a dot
            # segment only now; `as_uri()` would otherwise render one that
            # parses to a different path.
            decoded = _remove_dots(decoded, scheme)
        path = decoded
        if fragment is not None:
            fragment = uritools.uridecode(fragment, errors=_ERRORS)
        return source, path, Query.parse(query or ""), fragment or ""

    @property
    def parts(self):
        """The tuple of URI components: (source, path, query, fragment)."""
        return (self.source, self.path, self.query, self.fragment)

    def _load_parts(self):
        """Join semantics (documented in docs/divergences.md -- deliberate, not
        RFC 3986 reference resolution): multiple constructor arguments are
        joined pathlib-`joinpath`-style, right to left, stopping at the
        first absolute segment, and then RFC 3986 5.2.4 removes the dot
        segments of the joined path (`URI("http://h/d/", "../x")` is
        `http://h/x`). `source` is taken from the last (rightmost) segment
        that has one; `query`/`fragment` likewise come from the last
        segment that actually sets one (a later segment with no
        query/fragment does not blank out an earlier one).
        """
        uris = self._raw_uris
        source = _NOSOURCE
        query = fragment = None
        _path = ""
        local = False

        if not uris:
            pass
        elif len(uris) == 1 and isinstance(uris[0], URI):
            source, _path, query, fragment = uris[0].parts
        else:
            paths: list[tuple[str, bool]] = []
            for _uri in uris:
                src, path, q, frag = (
                    _uri.parts if isinstance(_uri, URI) else self._parse_uri(_uri)
                )
                local = local or isinstance(_uri, _RelativeLocalPath)
                if bool(src):
                    source = src
                if q:
                    query = q
                if frag:
                    fragment = frag
                # A `URI` argument says what restarts a join for its own
                # scheme (a `FileURIPath` stores "D:/f" without the "/").
                absolute = (
                    _uri._is_absolute_decoded(path)
                    if isinstance(_uri, URI)
                    else path.startswith("/")
                )
                paths.append((path, absolute))

            for path, absolute in reversed(paths):
                if not path:
                    continue
                if path.endswith("/"):
                    _path = f"{path}{_path}"
                elif _path:
                    _path = f"{path}/{_path}"
                else:
                    _path = path
                if absolute or _path.startswith("/"):
                    break

            if local and not source:
                # Nothing but relative local paths and sourceless strings:
                # still a local file.
                source = _FILE_SOURCE

        if (
            (source.host or source.userinfo or source.port not in (None, ""))
            and _path
            and not _path.startswith("/")
        ):
            _path = "/" + _path

        if len(uris) > 1 and _has_dot_segment(_path) and source.scheme != "data":
            # Each argument was resolved on its own; a `..` in one can now
            # climb out of what precedes it.
            _path = _remove_dots(_path, source.scheme)

        self._init(source, _path, query, fragment)

    def _init(
        self,
        source: Source,
        path: str,
        query: Query | str | None,
        fragment: str,
        **kwargs,
    ):
        # Re-init of an initiated instance is relied upon (`with_source()` runs
        # `_init()` a second time over the first): audit every call site before making
        # it raise. `_initiated` is set LAST: the properties read the raw slots once set.
        if query.__class__ is not Query:
            query = Query.parse(query) if query else _NO_QUERY
        fragment = fragment or ""
        if (
            self._initiated
            and path == self._path
            and fragment == self._fragment
            and str(query) == str(self._query)
            and source == self._source
        ):
            # A second thread finishing its own first parse stores what is
            # already there: resetting the caches would undo the first
            # thread's, and a reader between the two would find them empty.
            return
        self._source = source
        self._path = path
        self._query = query
        self._fragment = fragment
        self._uri = None
        self._normalized_path = None
        self._segments_cache = None
        self._suffix_cache = None
        self._stem_cache = None
        self._initiated = True

    def _from_parsed_parts(
        self, source: Source, path: str, query: str, fragment: str, /, **kwargs
    ):
        cls = type(self)
        uri = cls.__new__(cls)
        uri._init(source, path, query, fragment, **kwargs)
        return uri

    def _from_decoded_path(self, path: str, /, **kwargs) -> "_ty.Self":
        """Build a same-type URI whose `.path` is `path` verbatim.

        `path` is an **already-decoded path string**, not URI syntax: `?`,
        `#`, `%` and `:` are ordinary filename characters here. Only
        path-level normalization (dot segments, exactly what `_parse_uri`
        applies *after* decoding) is performed -- nothing is split off and
        nothing is percent-decoded.

        This is what a destination/target argument must go through.
        Feeding such a string back into the URI parser (`URI(path)`,
        `type(self)(path)`) reads it as syntax: "a?b.txt" silently became
        "a" plus a query, "a#b.txt" became "a" plus a fragment,
        "a%20b.txt" became "a b.txt", and a relative "C:/Temp/x" became
        scheme "c" plus "/Temp/x" -- so the wire call went to a different
        file than the caller named, with no error. Percent-encoding the
        string before parsing would fix the truncation but re-encode an
        already-encoded name (a literal "%20" would come back as a space),
        so the parse is bypassed instead of being fed encoded input.
        """
        return self._from_parsed_parts(
            _NOSOURCE, _remove_dot_segments(path), None, None, **kwargs
        )

    def _is_absolute_decoded(self, path: str) -> bool:
        """Whether a decoded path string restarts the join. A leading "/"
        does; `FileURIPath` also accepts a Windows drive ("C:/x")."""
        return path.startswith("/")

    def _join_decoded(self, key: str) -> "URI":
        """Join `key` as an already-decoded path, one segment at a time.

        Each name goes through `_make_child_relpath()` -- what `iterdir()`
        uses -- so a hand-typed name and a listed one are built by the same
        code, including in schemes that give a name special meaning
        (`gitlab:`'s "-"). An absolute key restarts from the root of this
        same source. A key with `.` or `..` segments is joined as a whole
        and has them removed as RFC 3986 5.2.4 says (`_join_dotted`). An empty
        segment inside the key is a segment (`x//y` is `x//y`, RFC 3986 3.3):
        the constructor and a `URI` argument keep it, and on an object store
        `d//y` and `d/y` are two keys.

        A `data:` payload is an opaque octet string, so it never gets
        segment treatment: the key is appended verbatim, exactly as
        `_parse_uri` declines to normalize it.
        """
        if not key:
            return self
        if self.source.scheme == "data":
            path = self.path
            if path and not path.endswith("/"):
                path += "/"
            return self._from_parsed_parts(
                self.source, path + key, self.query, self.fragment
            )
        segments = key.split("/")
        absolute = self._is_absolute_decoded(key)
        if absolute and segments[0] == "":
            segments = segments[1:]  # the root, which the join starts from
        if "." in segments or ".." in segments:
            return (self.with_path("/") if absolute else self)._join_dotted(segments)
        if type(self)._make_child_relpath not in _DEFAULT_CHILD_BUILDERS:
            return self._join_children(segments, absolute)
        # Nothing special about a child: the path is written once.
        path = "/" if absolute else self.path
        has_authority = self._has_authority()
        empty = 0
        for segment in segments:
            if not segment:
                empty += 1
                continue
            if empty:
                path += "/" * _empty_slashes(path, empty, True)
                empty = 0
            path = _child_path(path, segment, has_authority)
        if empty:
            # A trailing "/" is load-bearing: for http/dav it is how a
            # directory URL is spelled, and `name`/`parent` are documented
            # to keep it (see docs/divergences.md).
            path += "/" * _empty_slashes(path, empty, False)
        return self._from_parsed_parts(self.source, path, self.query, self.fragment)

    def _join_children(self, segments: "list[str]", absolute: bool) -> "URI":
        """`_join_decoded()` for a scheme that overrides
        `_make_child_relpath()`: it is asked for every name, one child at a
        time, exactly as a listing asks it."""
        result = self.with_path("/") if absolute else self
        empty = 0
        for segment in segments:
            if not segment:
                empty += 1
                continue
            if empty:
                result = result._with_empty_segments(empty, between=True)
                empty = 0
            result = result._make_child_relpath(segment)
        if empty:
            result = result._with_empty_segments(empty, between=False)
        return result

    def _with_empty_segments(self, count: int, *, between: bool) -> "URI":
        """This URI with `count` empty segments after its path."""
        path = self.path
        slashes = _empty_slashes(path, count, between)
        return self.with_path(path + "/" * slashes) if slashes > 0 else self

    def _join_dotted(self, segments: "list[str]") -> "URI":
        """`_join_decoded()` for a key holding `.` or `..` segments.

        The key is concatenated pathlib-style (`/d` + `x` is `/d/x`, whether
        or not `/d` ends in a slash) and the dot segments of the whole path
        are then removed, so `/d/` + `../x` is `/x` and `/d/x` + `..` is
        `/d/`: the same answer the constructor gives for that spelling.
        The names the key adds that survive are built as children of what
        is left of this path."""
        given = [segment for segment in segments if segment]
        base = self.path or ("/" if self._has_authority() else "")
        if base and not base.endswith("/"):
            base += "/"
        # A key ending in a slash, `.` or `..` names a directory.
        trailing = segments[-1] in ("", ".", "..")
        joined = base + "/".join(segments)
        final = _remove_dots(joined, self.source.scheme)
        names: list[str] = []
        for segment in given:
            if segment == "..":
                if names:
                    names.pop()
            elif segment != ".":
                names.append(segment)
        parts = final.split("/")
        tail = names + [""] if trailing else names
        if not names or parts[-len(tail) :] != tail:
            return self.with_path(final)
        head = "/".join(parts[: -len(tail)])
        if not head and final.startswith("/"):
            head = "/"
        result = self
        if head not in (self.path, self.path.rstrip("/")):
            result = self.with_path(head)
        for name in names:
            result = result._make_child_relpath(name)
        if trailing and not result.path.endswith("/"):
            result = result.with_path(result.path + "/")
        return result

    def _join_arg(self, arg):
        """A join argument, with a `str`/`bytes` read as an already-decoded
        path rather than URI syntax.

        `/` and `joinpath()` name a child the way `iterdir()` does, so a
        name containing `?`, `#`, `%` or a leading `C:` joins verbatim. A
        `URI` argument keeps full URI semantics -- that is how a caller asks
        for a scheme-aware join, e.g. `base / URI("s3://bucket/key")`.
        """
        if isinstance(arg, bytes):
            arg = arg.decode()
        return arg

    def _rename_target(self, target: URILike) -> "URI":
        """Normalize a `rename()`/`replace()` destination to a `URI`.

        A `str` is an already-decoded path (see `_from_decoded_path`), and
        a relative one is resolved against `self.parent` -- the documented
        sibling-rename semantics ("rename this to a new name in the same
        directory"), not against `self` itself. A `URI` (of any scheme
        class) is taken as given; anything else goes through `URI(...)`,
        which is lossless for `PurePath`/`os.PathLike` (they are
        percent-encoded on the way in and decoded back out).
        """
        if isinstance(target, URI):
            result = target
        else:
            if isinstance(target, str):
                # The join `copy()` and `move()` use for a path destination, so dot segments
                # resolve here too: `rename("../b")` must not send a literal "sub/../b",
                # which an object store reads as another key.
                result = self._sibling_base()._join_decoded(target)
            else:
                # target is a URI by now, so this join re-uses `_load_parts`'
                # existing right-to-left semantics without re-parsing it.
                result = URI(self._sibling_base(), target)
        if not self._same_location(result):
            # Every scheme renames over its own connection or bucket using only
            # `target.path`, so a target elsewhere would be renamed in the wrong place;
            # NotImplementedError is move()'s signal to copy and delete instead.
            raise NotImplementedError(
                f"rename() cannot cross locations: {self} -> {result}"
            )
        return result

    def _sibling_base(self) -> "URI":
        """The directory a relative destination is resolved against: the
        parent without its query and fragment, which are good for this
        resource only (a signature in the query does not sign a sibling)."""
        parent = self.parent
        return parent._from_parsed_parts(parent.source, parent.path, None, None)

    def _same_location(self, other: "URI") -> bool:
        """Whether `other` lives where a native `rename()` of `self` can
        reach it: the same endpoint (see `_same_authority`), or a sourceless
        path relative to `self`. Schemes whose namespace is narrower than the
        authority (an archive, an Azure container) override this."""
        return not other.source or _same_authority(self.source, other.source)

    @classmethod
    def _format_parsed_parts(
        cls,
        source: Source,
        path: str,
        query: Query | str | None,
        fragment: str,
        /,
        sanitize=True,
    ) -> str:
        # Direct string assembly, not uricompose()'s re-validation: the parts come from
        # a parse or from our own normalized join state (see `_compose_uri` in
        # source/_compose.py for the equivalence notes).
        scheme, userinfo, host, port = _source_parts(source, sanitize)
        return _compose_uri(
            scheme,
            userinfo,
            host,
            port,
            path,
            str(query) if query else None,
            fragment or None,
        )

    def __str__(self):
        """Return the string representation of the path. Deliberately
        sanitized (password dropped from userinfo) since `str()` is what
        logging/printing reach for -- this does NOT round-trip a
        credentialed URI. Use `as_uri(sanitize=False)` for the full URI
        including credentials."""
        return self.as_uri(sanitize=True)

    def __fspath__(self):
        if (self.source.scheme or "file") == "file":
            host = self.source.host
            if not host or (isinstance(host, str) and host.lower() == "localhost"):
                path = self.path
                # "file://localhost/C:/x" keeps the "/" before its drive (it
                # must, to render with an authority); the OS path does not.
                if (
                    os.name == "nt"
                    and path.startswith("/")
                    and _is_drive(path[1:].partition("/")[0])
                ):
                    path = path[1:]
                return path
            elif os.name == "nt":
                # A named host is a UNC share even when it is this machine:
                # "file://fileserver/share/x" is "//fileserver/share/x", never
                # "/share/x" on the current drive. No DNS lookup either.
                return f"//{host}/{self.path.removeprefix('/')}"
            elif self.is_local():
                return self.path
            else:
                raise NotImplementedError("OS Support for not local fspath")

        if self._host_filesystem_path:
            return self.path

        raise NotImplementedError(f"fspath for {self.source.scheme}")

    def host_fspath(self) -> str:
        """Return `.path` for any scheme whose path component is a
        filesystem path on the URI's own host (see `_host_filesystem_path`),
        for building a command line that runs *on that host* (e.g. via a
        remote executor). Unlike `__fspath__`, this never falls back to
        treating the path as local -- it raises `NotImplementedError` for
        schemes with no host-filesystem meaning (`http:`, `s3:`, ...)."""
        if self._host_filesystem_path:
            return self.path
        raise NotImplementedError(f"host_fspath for {self.source.scheme}")

    def __repr__(self):
        try:
            return "{}({!r})".format(type(self).__name__, str(self))
        except Exception:
            # A URI that does not parse still has to print.
            return super().__repr__()

    def as_uri(self, /, sanitize=False):
        if self._uri is None or sanitize:
            path = self.path
            if path.startswith("//") and not self._has_authority():
                # Without an authority a "//" path would render as one ("file:////srv/x" is
                # host "" and path "//srv/x") and str()/repr()/hash() would raise; "/." keeps
                # it a path that parses back to the same one.
                path = "/." + path
            uri = self._format_parsed_parts(
                self.source, path, self.query, self.fragment, sanitize=sanitize
            )
            if not sanitize:
                self._uri = uri
            return uri
        else:
            return self._uri

    @property
    def source(self) -> Source:
        if not self._initiated:
            self._load_parts()
        return self._source

    @property
    def path(self) -> str:
        if not self._initiated:
            self._load_parts()
        return self._path

    @property
    def query(self) -> Query:
        """The query exactly as received: still percent-encoded, so an
        escaped `&`, `=` or `+` inside a value survives the round trip. Use
        `Query.to_pairs()`/`to_dict()` for decoded pairs."""
        if not self._initiated:
            self._load_parts()
        return self._query

    @property
    def fragment(self) -> str:
        if not self._initiated:
            self._load_parts()
        return self._fragment

    def _make_child_relpath(self, name: str, **kwargs) -> _ty.Self:
        new_path = _child_path(self.path, name, self._has_authority())
        # Through `_from_parsed_parts`, so a scheme that carries per-instance
        # state rebuilds it (`SFTPURIPath._ssh_config`); `/` walks segments
        # through here. The query and fragment stay, as in every path-only
        # derivation.
        return self._from_parsed_parts(
            self.source, new_path, self.query, self.fragment, **kwargs
        )

    def with_source(self, source: Source):
        """Return a new URI with the source replaced."""
        return self._from_parsed_parts(source, self.path, self.query, self.fragment)

    def with_segments(self, *segments: "str | os.PathLike"):
        """Return a new URI with the path segments replaced.

        The segments are the spelling `segments` returns (a leading `""` is
        the root), joined with `/`; an element may also be `bytes`, a
        `PurePath`, a `Pathname` or an `os.PathLike`, whose posix text is
        used."""
        if not segments:
            return self.with_path("")
        return self.with_path("/".join(_segment_text(item) for item in segments))

    def with_path(self, path: str | Pathname):
        """Return a new URI with the path replaced; under an authority a
        relative path gets the leading `/` the constructor gives it."""
        if not isinstance(path, str):
            path = _segment_text(path)
        if path and not path.startswith("/") and self._has_authority():
            path = "/" + path
        return self._from_parsed_parts(self.source, path, self.query, self.fragment)

    def with_query(self, query: "QueryLike | None"):
        """Return a new URI with the query replaced.

        A `str` is taken in the percent-encoded form `.query` returns and is
        sent as given; a mapping or a sequence of pairs is encoded by
        `Query`; `None` removes the query."""
        query = _coerce(query)
        return self._from_parsed_parts(self.source, self.path, query, self.fragment)

    def with_fragment(self, fragment: str):
        """Return a new URI with the fragment replaced."""
        return self._from_parsed_parts(self.source, self.path, self.query, fragment)

    # The cached properties return the local they computed, never the slot
    # read back: another thread's `_init` may have reset it in between.
    @property
    def segments(self):
        segments = self._segments_cache
        if segments is None:
            path = self.path
            segments = tuple(path.split("/")) if path else ()
            self._segments_cache = segments
        return segments

    @property
    def suffix(self) -> str:
        suffix = self._suffix_cache
        if suffix is None:
            suffix = self._suffix_cache = _name_suffix(self.name)
        return suffix

    @property
    def stem(self) -> str:
        stem = self._stem_cache
        if stem is None:
            stem = self._stem_cache = _name_stem(self.name)
        return stem

    @property
    def parent(self):
        """The logical parent of the path."""
        segments = self.segments
        if not segments or len(segments) == 2 and segments[1] == "":
            return self
        if len(segments) == 2 and segments[0] == "":
            # "/a" -> "/", not "": the empty path is relative, so the parent
            # of a top-level FileURIPath resolved to the current directory and
            # `parents` never reached the root.
            return self.with_path("/")
        return self.with_path("/".join(segments[:-1]))

    def _has_authority(self) -> bool:
        source = self.source
        return bool(source.host or source.userinfo or source.port not in (None, ""))

    def _match_parts(self) -> tuple[bool, list[str]]:
        # An authority with an empty path ("http://h") is that authority's
        # root, the same as "http://h/" (RFC 3986). The host itself is never
        # part of what match() sees.
        anchored, names = super()._match_parts()
        return anchored or (not self.path and self._has_authority()), names

    def _prefix_segments(self) -> list[str]:
        """Segments for `is_relative_to`/`relative_to` prefix comparison:
        `[""]` for a root (including an authority with an empty path), `[]` for
        the empty relative path."""
        if not self.path:
            return [""] if self._has_authority() else []
        path = self.normalized_path
        return [] if path == "." else _segments_of(path)

    @property
    def normalized_path(self):
        """Return the normalized path using posixpath rules."""
        if self._normalized_path is None:
            self._normalized_path = _posix.normpath(self.path)
        return self._normalized_path

    def is_absolute(self):
        """True if the path is absolute: it starts with "/", with or without
        a source (as `PurePosixPath("/a")` is absolute)."""
        return self.path.startswith("/")

    def is_relative_to(self, other: URILike):
        """Return True if the path is relative to another path or False."""
        # `other` is parsed standalone (`URI(other)`), not anchored at self's root, as
        # `relative_to()` and CPython do. A standalone parse leaves `other.source`
        # empty, which the guard below treats as compatible with any `self.source`.
        other = other if isinstance(other, URI) else URI(other)
        if not (
            (other.source == self.source)
            or not (bool(self.source) and bool(other.source))
        ):
            return False
        # Segment-wise prefix comparison: a naive startswith() on the raw
        # strings would report "/foo/bar2" as relative to "/foo/bar".
        _other = other._prefix_segments()
        _self = self._prefix_segments()
        if _self[:1] == [""] and _other[:1] != [""]:
            # An absolute path is never relative to a relative one (the
            # empty relative path included), as in pathlib.
            return False
        return _self[: len(_other)] == _other

    def relative_to(self, other: URILike, *, walk_up=False):
        other = other if isinstance(other, URI) else URI(other)
        # No upfront `is_relative_to()` check: the step==0 iteration (path=other)
        # raises the same error, and an early one would skip the walk_up loop.
        for step, path in enumerate([other] + list(other.parents)):
            if self.is_relative_to(path):
                break
            elif not walk_up:
                raise ValueError(
                    f"{str(self)!r} is not in the subpath of {str(other)!r}"
                )
            elif path.name == "..":
                raise ValueError(f"'..' segment in {str(other)!r} cannot be walked")
        else:
            raise ValueError(f"{str(self)!r} and {str(other)!r} have different anchors")
        # `_prefix_segments()`, not raw `.segments`: the latter gives the URI root ("/")
        # a spurious 2-tuple ("", ""), and `relative_to(<root>)` would drop the
        # child's only real segment.
        self_segs = self._prefix_segments()
        path_segs = path._prefix_segments()
        parts = [".."] * step + self_segs[len(path_segs) :]
        return self._from_parsed_parts(
            _NOSOURCE, "/".join(parts), self.query, self.fragment
        )

    def is_local(self):
        """Return True if the URI points to a local resource."""
        return self.source.is_local()

    def __eq__(self, other: URI | str):
        # Only a URI or a URI string, which hash as their URI text like __hash__;
        # another Pathname (MemPath, LocalPath) hashes by its own rule, and a
        # relative LocalPath's as_uri() raises.
        if isinstance(other, URI):
            uri = other.as_uri()
        elif isinstance(other, str):
            uri = other
        else:
            return NotImplemented
        return self.as_uri() == uri

    def __hash__(self):
        return hash(self.as_uri())

    def _order_key(self):
        return self.as_uri()

    def _join_object(self, *parts) -> "URI":
        """A new URI of this class from `parts`, joined as the constructor
        joins them. `URIPath` also chooses the class from the result's
        scheme, so joining an absolute local path gives a `FileURIPath`."""
        return type(self)(*parts)

    def __truediv__(self, key):
        """`uri / "name"`. A `str` is a decoded path segment, never URI
        syntax: "a?b.txt" is a filename, not a query (`URI._join_arg`). Any
        other argument is joined as the constructor joins it."""
        # Only converting `key` decides NotImplemented: catching TypeError
        # around the whole construction would turn a bug inside a scheme's
        # __new__/_init into "unsupported operand type(s) for /".
        key = self._join_arg(key)
        if isinstance(key, str):
            return self._join_decoded(key)
        try:
            converted = _as_uri(key)
        except (TypeError, NotImplementedError):
            return NotImplemented
        return self._join_object(self, *converted._raw_uris)

    def joinpath(self, *args):
        """Combine this URI with segments; a `str` is a decoded path (see
        `URI._join_arg`), anything else is joined as the constructor joins
        it -- pass a `URI` for a scheme-aware join."""
        result = self
        for arg in args:
            arg = result._join_arg(arg)
            if isinstance(arg, str):
                result = result._join_decoded(arg)
            else:
                result = result._join_object(result, *_as_uri(arg)._raw_uris)
        return result

    def __rtruediv__(self, key: str):
        """`"prefix" / uri`. The str is a decoded path joined in front of
        this one, never URI syntax (so "C:/x" is not read as a scheme)."""
        if not isinstance(key, str):
            return NotImplemented
        # A plain URI: building the prefix must not touch `self.backend`.
        return self._join_object(URI()._from_decoded_path(key), self)

    def as_posix(self):
        source = self.source
        host = None
        posix = self.path
        if source.host:
            host = source.host
            user, password = source.parsed_userinfo()
            if user:
                posix = f"{user}@{host}:{posix}"
            else:
                posix = f"{host}:{posix}"
        return posix


URI._slot_names = _slot_names(URI)


#: The `_make_child_relpath` implementations that only write a child's path:
#: a class with any other builds a joined key one child at a time
#: (`URI._join_children`). The module that defines a class with such a builder
#: adds it.
_DEFAULT_CHILD_BUILDERS = {URI._make_child_relpath}
