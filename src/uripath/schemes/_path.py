"""`URIPath`: the class a URI scheme subclasses, and the backend bookkeeping it shares between the paths of one endpoint."""

from __future__ import annotations

import stat as _stat
import threading as _threading
import typing as _ty
import weakref as _weakref
import re as _re

from pathlib_next import FileStat, Path
from pathlib_next import providers as _providers
from .._uri import URI, URILike
from .._uri import _DEFAULT_CHILD_BUILDERS
from ..exceptions import UnsupportedSchemeError
from ..source import Source
from ..source._source import _same_authority
from ._registry import (
    _BUILTIN_SCHEMES,
    _CLAIMS,
    _CLAIMS_LOCK,
    _ENTRY_POINTS_LOADED,
    _claim_schemes,
    _declared_entry_points,
    _forget_entry_points,
)

if _ty.TYPE_CHECKING:
    from typing import Self


#: An RFC 3986 scheme followed by its colon, used to tell a URI destination
#: from a path one (see `_looks_like_uri`).
_URI_SCHEME_RE = _re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")


#: Backends a path built for itself through `_initbackend()`, by `id()` (the `is`
#: test on lookup makes a reused id harmless). It covers a derived backend that
#: a scheme hands on through `backend=`, which would read as supplied.
_DERIVED_BACKENDS: "_weakref.WeakValueDictionary[int, object]" = (
    _weakref.WeakValueDictionary()
)


class DerivedBackend:
    """Marks a backend class whose instances only ever come from
    `_initbackend()`, for a backend that cannot be weakly referenced and so
    cannot be recorded in `_DERIVED_BACKENDS` (a tuple, say)."""

    __slots__ = ()


_DerivedBackend = DerivedBackend


class _BackendCell:
    """The slot that paths derived from one another on one endpoint share for
    the backend they derive for themselves. It starts empty, so deriving a
    path builds nothing; the first of them to need a backend fills it and the
    rest read it. `lock` makes two threads that ask at once build one."""

    __slots__ = ("backend", "lock")

    def __init__(self):
        self.backend = None
        self.lock = _threading.RLock()


#: Makes "create the cell of a path unless it has one" atomic.
_CELL_LOCK = _threading.Lock()


def _rebuild_path(cls, uri, options, backend, schemesmap):
    """Unpickle a `URIPath`: the class built from its URI text again."""
    if backend is not None:
        options = {**options, "backend": backend}
    if schemesmap is not None:
        options = {**options, "schemesmap": schemesmap}
    return cls(uri, **options)


def _looks_like_uri(value: str, schemesmap=None) -> bool:
    """Whether a destination string is URI syntax rather than a path.

    Needs an RFC 3986 scheme prefix; without `://` the scheme must also be
    one a class registers, so an ordinary relative name whose first segment
    happens to carry a colon (`notes:draft`, `Fedora-42:latest.tar`) stays a
    path. A one-letter scheme is a Windows drive (`C:/Temp`). Same rule
    the `uripath` command applies to its arguments.
    `schemesmap` is the allow-list the scheme is looked up in, if any.
    """
    match = _URI_SCHEME_RE.match(value)
    if match is None:
        return False
    if match.end() == 2:  # "C:" -- a drive, not a scheme
        return False
    if "://" in value:
        return True
    scheme = value[: match.end() - 1].lower()
    try:
        return (
            Source(scheme, None, None, None).get_scheme_cls(schemesmap) is not URIPath
        )
    except Exception:
        # A scheme plugin that fails to load: treat it as a URI, as the
        # scheme lookup would have.
        return True


class URIPath(URI, Path):
    """`URI` + `Path` (I/O) + scheme dispatch. `URIPath(...)` constructs
    the concrete subclass registered for the URI's scheme (via `__SCHEMES`)
    -- e.g. `URIPath("http://...")` returns an `HTTPURIPath`. Subclass this
    and set `__SCHEMES` to add a new scheme (Track B of extending this
    library; see `docs/guides/extending.md`): defining the class registers
    it, a name another class holds raises `ValueError` unless the class
    statement passes `replace=True`, and `schemes()` / `scheme_class()` read
    the registry. Implement the I/O surface
    (`_listdir` or `_scandir`, `stat`, `_open`, ...) documented in
    `docs/guides/extending.md`. Prefer overriding `_scandir()` over `_listdir()` when the
    listing call already returns type/size/mtime metadata (PROPFIND, MLSD,
    `listdir_attr`, an S3 list page, ...) -- `walk()`/`glob()` then answer
    `is_dir()` on the results for free, without a stat request per entry."""

    #: Slots: `_backend` (None until built or inherited), `_backend_derived` (the path
    #: built it), `_backend_candidates` (join segments' backends until the endpoint is
    #: known), `_derived_cell` (shared on one endpoint), `_schemes_in_use` (`schemesmap=`).
    __slots__ = (
        "_backend",
        "_backend_derived",
        "_backend_candidates",
        "_derived_cell",
        "_stat_hint",
        "_schemes_in_use",
    )
    __SCHEMES: _ty.Sequence[str] = ()

    def __init_subclass__(cls, replace: bool = False, **kwargs):
        super().__init_subclass__(**kwargs)
        _claim_schemes(cls, replace)
        _forget_entry_points()

    @classmethod
    def schemes(cls) -> "tuple[str, ...]":
        """The registered scheme names, sorted: those of every class defined
        so far, every built-in scheme and every entry point of the
        `uripath.schemes` group, whether or not its module is imported
        yet. The schemes another distribution provides are listed too."""
        from . import _elsewhere

        with _CLAIMS_LOCK:
            claimed = list(_CLAIMS)
        return tuple(
            sorted(
                {
                    *claimed,
                    *_BUILTIN_SCHEMES,
                    *_elsewhere.SCHEMES,
                    *_declared_entry_points(),
                }
            )
        )

    @classmethod
    def scheme_class(cls, name: str) -> "type[URIPath]":
        """The class registered for the scheme `name` (case-insensitive),
        importing its module or loading its entry point first when needed.

        Raises `UnsupportedSchemeError` naming the registered schemes when there is
        none, and `ImportError` for a built-in module that cannot be
        imported and for a scheme another distribution provides that is not
        installed (the error names what to install).
        """
        found = cls._find_scheme(name.lower(), strict=True)
        if found is None:
            raise UnsupportedSchemeError(
                f"no URI scheme {name!r} is registered; registered: "
                + ", ".join(cls.schemes())
            )
        return found

    @classmethod
    def _find_scheme(cls, scheme: str, strict: bool = False):
        """The class that registered `scheme`, or `None`: a class already
        defined, then the built-in module, then an entry point, then the class
        that stands for a scheme another distribution provides. With `strict`
        a built-in module that fails to import, and a scheme provided
        elsewhere that is not installed, raise instead of reading as "no
        class" and as that stand-in."""
        found = _CLAIMS.get(scheme)
        if found is None and (
            cls._load_builtin_scheme(scheme, strict=strict)
            or cls._load_entry_point(scheme)
        ):
            found = _CLAIMS.get(scheme)
        if found is None:
            from . import _elsewhere

            if scheme not in _elsewhere.SCHEMES:
                return None
            if strict:
                raise _elsewhere.not_installed(scheme)
            found = _elsewhere.ProvidedElsewhere
        return found

    @classmethod
    def _schemes(cls) -> _ty.Sequence[str]:
        try:
            return getattr(cls, f"_{cls.__name__}__SCHEMES")
        except AttributeError:
            return ()

    @classmethod
    def _load_entry_point(cls, scheme: str) -> bool:
        """Attempt to load a scheme class from package entry points.

        Looks for entry points in the 'uripath.schemes' group where
        the name matches the requested scheme.
        """
        ep = _declared_entry_points().get(scheme)
        if ep is None or scheme in _ENTRY_POINTS_LOADED:
            return False
        ep.load()
        _ENTRY_POINTS_LOADED.add(scheme)
        return True

    @classmethod
    def _load_builtin_scheme(cls, scheme: str, strict: bool = False) -> bool:
        """Attempt to load a builtin scheme module dynamically on-demand."""
        module_name = _BUILTIN_SCHEMES.get(scheme)
        if module_name:
            import importlib

            try:
                importlib.import_module(module_name)
                return True
            except ImportError:
                if strict:
                    raise
        return False

    def __new__(
        cls,
        *args,
        schemesmap: "_ty.Mapping[str, type[URIPath]] | None" = None,
        findclass=False,
        **kwargs,
    ) -> "URIPath":
        if cls is URIPath or findclass:
            uri = URI(*args, **kwargs)
            cls: type[URIPath] = uri.source.get_scheme_cls(schemesmap)
            if cls is URIPath:
                inst = URI.__new__(cls, *args, **kwargs)
            else:
                inst = cls.__new__(cls, *args, **kwargs)
            inst._schemes_in_use = schemesmap
            inst._init(uri.source, uri.path, uri.query, uri.fragment, **kwargs)
        else:
            inst = URI.__new__(cls, *args, **kwargs)
            inst._schemes_in_use = schemesmap
            backend = kwargs.get("backend", None)
            if backend is not None:
                inst._backend = backend
            else:
                # Which of these a path inherits depends on the endpoint it
                # ends up with, known once it is parsed (`_inherit_backend`).
                for segment in args:
                    if isinstance(segment, cls):
                        if segment._backend_candidates is not None:
                            # Parsing the segment settles its own inheritance.
                            segment._load_parts()
                        if inst._backend_candidates is None:
                            inst._backend_candidates = []
                        inst._backend_candidates.append(
                            (segment, segment._backend, segment._backend_derived)
                        )
        return inst

    def _initbackend(self):
        return None

    def _inherit_backend(self, source: Source) -> None:
        """Settle which join segment's backend this path takes now that its
        endpoint is `source`: the rightmost one that holds a backend and
        belongs to that same endpoint (scheme, userinfo, host, port), else
        none. A backend never crosses to another endpoint, so credentials and
        sessions stay put. With none, the path joins the family of the
        rightmost segment on its endpoint (`_family_for()`)."""
        candidates = self._backend_candidates
        if candidates is None:
            return
        family = None
        for segment, backend, derived in reversed(candidates):
            if not _same_authority(segment.source, source):
                continue
            if backend is not None:
                self._backend, self._backend_derived = backend, derived
                family = None
                break
            if family is None and source:
                family = segment._family()
        if family is not None:
            self._derived_cell = family
        self._backend_candidates = None

    def _family(self) -> _BackendCell:
        """The cell this path and the paths derived from it share, made when
        it is first asked for."""
        cell = self._derived_cell
        if cell is None:
            with _CELL_LOCK:
                cell = self._derived_cell
                if cell is None:
                    cell = self._derived_cell = _BackendCell()
                    if self._backend is not None and self._backend_derived:
                        # Already built on its own: the family reads that one.
                        cell.backend = self._backend
        return cell

    def _family_for(self, source: Source) -> "_BackendCell | None":
        """The cell a path at `source` shares with this one: this path's own
        when `source` is its endpoint, else none. Never builds a backend, and
        a path that holds one hands that on instead (`_backend_for()`)."""
        if not self._initiated:
            self._load_parts()
        if self._backend is not None:
            return None
        mine = self._source
        if mine and (source is mine or _same_authority(source, mine)):
            return self._family()
        return None

    def _backend_for(self, source: Source):
        """`(backend, derived)` a path at `source` inherits from this one:
        what this path already holds, if `source` is its own endpoint, else
        `(None, None)`. Never builds a backend."""
        if not self._initiated:
            self._load_parts()
        backend = self._backend
        if backend is not None:
            mine = self._source
            if source is mine or _same_authority(source, mine):
                return backend, self._backend_derived
        return None, None

    def _from_parsed_parts(
        self, source: Source, path: str, query: str, fragment: str, /, **kwargs
    ):
        if "backend" in kwargs or (
            self._backend is None and self._backend_candidates is None
        ):
            # Given, or nothing to carry: the usual case before any I/O.
            inst = super()._from_parsed_parts(source, path, query, fragment, **kwargs)
            if "backend" not in kwargs:
                # A path that already has a family and stays on its own
                # source hands the cell on without asking again.
                cell = self._derived_cell
                inst._derived_cell = (
                    cell
                    if cell is not None and source is self._source
                    else self._family_for(source)
                )
        else:
            backend, derived = self._backend_for(source)
            if backend is not None:
                kwargs["backend"] = backend
            inst = super()._from_parsed_parts(source, path, query, fragment, **kwargs)
            if backend is not None and inst._backend is backend:
                inst._backend_derived = derived
            elif backend is None:
                inst._derived_cell = self._family_for(source)
        inst._schemes_in_use = self._schemes_in_use
        return inst

    def _init(
        self,
        source: Source,
        path: str,
        query: str,
        fragment: str,
        /,
        backend=None,
        **kwargs,
    ):
        self._inherit_backend(source)
        if backend is not None:
            self._backend = backend
            self._backend_derived = None
        super()._init(source, path, query, fragment, **kwargs)

    @property
    def backend(self):
        """The connection or session state backend instance."""
        if not self._initiated:
            # Settles a backend inherited from a join segment first.
            self._load_parts()
        backend = self._backend
        if backend is None:
            cell = self._derived_cell
            built = False
            if cell is None:
                backend = self._initbackend()
                built = backend is not None
            else:
                # The family builds one, whichever of them asks first.
                with cell.lock:
                    backend = cell.backend
                    if backend is None:
                        backend = self._initbackend()
                        if backend is not None:
                            cell.backend = backend
                            built = True
            if backend is not None:
                self._backend = backend
                self._backend_derived = True
                if built:
                    try:
                        _DERIVED_BACKENDS[id(backend)] = backend
                    except TypeError:
                        pass
        return backend

    def _supplied_backend(self):
        """The backend the caller gave this path (`backend=`,
        `with_backend()`, or inherited from a path that had one), or None
        when it has none yet or derived its own. Never builds one."""
        backend = self._backend
        if (
            backend is None
            or self._backend_derived
            or isinstance(backend, _DerivedBackend)
            or _DERIVED_BACKENDS.get(id(backend)) is backend
        ):
            return None
        return backend

    def _same_filesystem(self, other: "URIPath") -> bool:
        # A URI's equality includes its authority, so two paths built separately for one
        # URL are the same file; only two distinct SUPPLIED backends (separate
        # connections, or fakes for two hosts) are not provably the same tree.
        mine, theirs = self._supplied_backend(), other._supplied_backend()
        return mine is None or theirs is None or mine is theirs

    def _rename_compatible(self, target) -> bool:
        # Every scheme's `rename()` reads its target through
        # `_rename_target()`, which raises NotImplementedError for one it
        # cannot reach, so `move()` falls back to copy + delete by itself.
        return True

    def _coerce_target(self, target: str) -> "URIPath":
        """A `str` destination for `copy()`/`move()`, read by its shape.

        With a scheme (`s3://bucket/key`, `file:///tmp/x`) it is a URI, so a
        cross-scheme copy keeps working. Without one it is a decoded path on
        THIS endpoint -- absolute replaces the path, relative is a sibling,
        as `rename()` resolves it -- keeping this path's source and backend
        instead of building a sourceless path plus a second connection.

        A single-letter scheme is a Windows drive, not a scheme: `C:/Temp/x`
        is a path (the same rule the `uripath` CLI applies).
        """
        if _looks_like_uri(target, self._schemes_in_use):
            destination = type(self)(
                target, findclass=True, schemesmap=self._schemes_in_use
            )
            # Same endpoint: reuse the connection (and whatever auth was
            # configured on it) rather than opening a second, bare one.
            backend, derived = self._backend_for(destination.source)
            if backend is not None:
                destination._backend, destination._backend_derived = backend, derived
            else:
                destination._derived_cell = self._family_for(destination.source)
            return destination
        # `/` joins a decoded path on this endpoint and carries the backend.
        return self.parent / target

    def with_backend(self, backend):
        """Return a new path instance sharing the same backend state."""
        return self._from_parsed_parts(*self.parts, backend=backend)

    def _reduce_options(self) -> dict:
        """Constructor keywords a pickle rebuilds this path with, beside its
        URI text. A scheme with per-path state that is not a secret returns
        it here; the backend and the stat hint are never part of it."""
        return {}

    def __reduce__(self):
        # A path pickles as its URI text (userinfo included), never its connection. A
        # supplied backend goes along only if it declares `picklable = True`; a
        # derived one is rebuilt on demand.
        backend = self._supplied_backend()
        if backend is not None and getattr(backend, "picklable", False) is not True:
            backend = None
        return (
            _rebuild_path,
            (
                type(self),
                self.as_uri(sanitize=False),
                self._reduce_options(),
                backend,
                self._schemes_in_use,
            ),
        )

    def __copy__(self):
        # The same URI on the same backend object, supplied or derived: a
        # copy must not open a second connection or change which paths
        # `_same_filesystem()` places together.
        return self._from_parsed_parts(*self.parts)

    def __deepcopy__(self, memo):
        # A connection is not part of the value, so it is shared here too.
        inst = memo[id(self)] = self.__copy__()
        return inst

    def _join_object(self, *parts) -> "URIPath":
        # The class comes from the joined scheme, and from the allow-list.
        return type(self)(*parts, findclass=True, schemesmap=self._schemes_in_use)

    def with_source(self, source: Source):
        cls = type(self)
        if not source or not source.scheme:
            # Nothing to dispatch on (`source.scheme + ":"` raised TypeError
            # for a host-only Source): a plain URIPath.
            inst = URI.__new__(URIPath)
        elif source.scheme not in cls._schemes():
            inst = cls.__new__(
                cls,
                source.scheme + ":",
                findclass=True,
                schemesmap=self._schemes_in_use,
            )
        else:
            inst = cls.__new__(cls)
            backend, derived = self._backend_for(source)
            if backend is not None:
                inst._backend, inst._backend_derived = backend, derived
            else:
                inst._derived_cell = self._family_for(source)
        inst._schemes_in_use = self._schemes_in_use
        inst._init(source, self.path, self.query, self.fragment)
        return inst

    def _symlink_target(self, target: "URILike") -> "_ty.Self":
        """`Path._symlink_target()` for URI-backed paths: a `str` target is
        an already-decoded path, never URI syntax (see
        `URI._from_decoded_path`).

        The default `type(self)(target)` ran the link target back through
        the URI parser, so `symlink_to("/mnt/cache?v=2")` created a link
        pointing at `/mnt/cache`. Unlike `_rename_target()` this never
        anchors at `self.parent`: a symlink target is stored as given, so
        a relative one stays relative.
        """
        if isinstance(target, str):
            return self._from_decoded_path(target)
        return target

    @_providers.notimplemented
    def _listdir(self) -> "_ty.Iterator[str]": ...

    def _scandir(self) -> "_ty.Iterator[_ty.Tuple[str, _ty.Optional[FileStat]]]":
        """Default: derives from `_listdir()` + one `stat()` per child (no
        round-trip savings over `iterdir()`). Schemes whose listing
        call already returns metadata should override this directly instead
        (see docs/guides/extending.md) -- HTTPURIPath/DAVURIPath/SFTPURIPath/FTPURIPath/
        S3URIPath all do. A name that is not one path component
        (`providers.is_safe_child_name()`) is skipped, and an override must skip
        it too."""
        for name in self._listdir():
            # A listing is untrusted input: a name that is not one component
            # ("..", "a/b", "") must never become a child path.
            if not _providers.is_safe_child_name(name):
                continue
            child = self._make_child_relpath(name)
            try:
                # Non-following, like Path._scandir(): rm(recursive=True) and
                # walk() trust this stat, and a following one reported a
                # directory symlink as a real directory to descend into.
                stat = FileStat.from_path(child, follow_symlink=False)
            except OSError:
                stat = None
            yield name, stat

    def _make_child_relpath(
        self, name: str, stat_hint: "FileStat" = None, **kwargs
    ) -> _ty.Self:
        # The child takes the backend this path already holds and builds none
        # (`_from_parsed_parts`): naming a child is a pure-path operation. A
        # listing has one by the time it gets here, so its children share it.
        inst = super()._make_child_relpath(name, **kwargs)
        inst._stat_hint = stat_hint
        return inst

    def _pop_stat_hint(self) -> "FileStat | None":
        """Consume this instance's pre-seeded stat (from `_scandir()`), if
        any -- single-use: the next `stat()` call on this same object always
        re-fetches, so a live mutation is never masked by a stale hint. A
        type-only hint (`size_known` False) is consumed and not returned:
        `stat()` has to give a size and a time, which it does not hold."""
        hint = self._stat_hint
        self._stat_hint = None
        if hint is not None and not hint.size_known:
            return None
        return hint

    def _st_mode(self, *, follow_symlinks=True):
        # The type questions are answered by a type-only hint, without a request. The
        # hint answers a non-following stat, so it speaks for a followed one only when
        # the entry is not a link.
        hint = self._stat_hint
        if hint is not None and not hint.size_known:
            self._stat_hint = None
            mode = hint.st_mode
            if _stat.S_IFMT(mode) and (not follow_symlinks or not _stat.S_ISLNK(mode)):
                return mode
        return super()._st_mode(follow_symlinks=follow_symlinks)

    def iterdir(self) -> "_ty.Iterator[Self]":
        for name, stat in self._scandir():
            yield self._make_child_relpath(name, stat_hint=stat)


_DEFAULT_CHILD_BUILDERS.add(URIPath._make_child_relpath)
