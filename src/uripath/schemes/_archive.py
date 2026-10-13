from __future__ import annotations

import re as _re
import typing as _ty

from pathlib_next.archive import ArchivePath, LinkTarget, TarPath, ZipPath
from pathlib_next.providers import as_error_handler, check_follow
from .._uri import URI
from ..source import SAFE_PATH, Source, percent_encode
from ._path import URIPath
from ._delegate import DelegatingPath

_SEP = "!/"
_SCHEME_RE = _re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
# Every scheme an `ArchiveURIPath` class registers.
_ARCHIVE_SCHEMES = ("zip", "tar", "archive", "archive+zip", "archive+tar")


def _nesting_depth(archive_uri: str) -> int:
    """How many archive schemes `archive_uri` starts with: 1 for the
    `zip:file:///outer.zip!/inner.zip` of a nested archive, 0 otherwise."""
    depth = 0
    match = _SCHEME_RE.match(archive_uri)
    while match and archive_uri[: match.end() - 1].lower() in _ARCHIVE_SCHEMES:
        depth += 1
        archive_uri = archive_uri[match.end() :]
        match = _SCHEME_RE.match(archive_uri)
    return depth


def _split_archive_path(path: str) -> "tuple[str, str]":
    """Split `<archive-uri>!/<inner-path>` (Java-style separator, as used
    for JAR URLs / NIO ZipFileSystem) into its two halves. No separator (or
    a bare trailing "!") means the archive root.

    A nested archive's `<archive-uri>` is itself an archive URI with a
    separator of its own (`zip:file:///outer.zip!/inner.zip!/x.txt`): each
    leading archive scheme consumes one separator, and the split is at the
    next one. A member name containing `!/` is written `%21/`."""
    start = 0
    for _ in range(_nesting_depth(path)):
        index = path.find(_SEP, start)
        if index < 0:
            break
        start = index + len(_SEP)
    index = path.find(_SEP, start)
    if index >= 0:
        archive, inner = path[:index], path[index + len(_SEP) :]
    elif path.endswith("!") and len(path) - 1 >= start:
        archive, inner = path[:-1], ""
    else:
        archive, inner = path, ""
    return archive, inner


def _parse_archive_uri(raw: str, scheme: str) -> "tuple[str, str, object, str] | None":
    """Split a still percent-encoded `<scheme>:<archive-uri>!/<inner>`
    string at its first literal `!/` BEFORE anything is decoded, so each
    half is decoded exactly once: the outer by its own parse, the inner
    here. Returns (outer URI, decoded inner path, query, fragment), or None
    when `raw` does not start with `scheme`. An encoded `%21/` never
    separates, and the inner path's dot segments stop at the archive root."""
    prefix, sep, rest = raw.partition(":")
    if not sep or prefix.lower() != scheme:
        return None
    archive, inner = _split_archive_path(rest)
    _, path, query, fragment = URI._parse_uri("/" + inner.lstrip("/"))
    return archive, path.lstrip("/"), query, fragment


def _open_outer(archive_uri: str, schemesmap=None) -> "URIPath":
    if not _SCHEME_RE.match(archive_uri):
        raise ValueError(
            f"Archive URI {archive_uri!r} has no scheme -- prefix it "
            "explicitly, e.g. 'file:///path/to/archive.zip'."
        )
    return URIPath(archive_uri, schemesmap=schemesmap)


class ArchiveURIPath(DelegatingPath):
    """Common base for `zip:`/`tar:`/`archive:` archive paths:
    `<scheme>:<archive-uri>!/<inner-path>` (Java-style separator; the
    `<archive-uri>` half is itself any absolute URI with an explicit scheme
    -- `file:`, `http:`, `sftp:`, `ftp:`, ... -- so archives are readable
    straight off any existing backend). `segments`/`name`/`parent`/`glob`/
    ... all operate on the *inner* path; the outer archive handle is the
    `backend`, propagated through the normal backend machinery to every path
    derived from this one, and the members are read and written by a
    `pathlib_next.archive.ArchivePath` (`ZipPath` or `TarPath` once the format
    is known) on that handle.

    Also registered directly as the `archive:` catch-all scheme (see
    `__SCHEMES` below): `zip:`/`tar:` (via `ZipURIPath`/`TarURIPath`, which just
    pin `_core_cls`) fix the format; plain `archive:` leaves it undecided
    and settles it on first use. Writes are gated on the handle being
    writable, which only a zip archive that is a local `file:` ever is -- so a
    tar-backed instance, whether reached via `tar:` or auto-detected via
    `archive:`, correctly raises `NotImplementedError` on any write attempt
    rather than silently misbehaving."""

    __SCHEMES = ("archive",)
    __slots__ = ()
    _core_cls: type = ArchivePath
    _DELEGATED = (
        "_scandir",
        "_listdir",
        "_open",
        "_mkdir",
        "unlink",
        "rmdir",
        "_write_batch",
        "_node_key",
    )

    def _backend_for(self, source):
        backend, derived = super()._backend_for(source)
        if backend is None and not source:
            # The sourceless `relative_to()` result is still a member path of
            # this archive: its handle is what `_init` reads as "derived".
            backend, derived = self._backend, self._backend_derived
        return backend, derived

    def _init(self, source, path, query, fragment, /, **kwargs):
        self._inherit_backend(source)
        backend = kwargs.get("backend", None) or self._backend
        if backend is None:
            # A fresh top-level construction: split the original, still-encoded string when
            # there is one; `path` was decoded and dot-normalized as a whole, which merged
            # the outer's query into ours and decoded the outer twice.
            raw = self._raw_uris
            parsed = None
            if raw and len(raw) == 1 and isinstance(raw[0], str):
                parsed = _parse_archive_uri(raw[0], source.scheme)
            if parsed is not None:
                archive_str, inner, query, fragment = parsed
            else:
                archive_str, inner = _split_archive_path(path)
                inner = inner.lstrip("/")
            outer = _open_outer(archive_str, self._schemes_in_use)
            # `ZipURIPath`/`TarURIPath` pin the format; for `archive:` it is settled on
            # first use, so building the path reads nothing.
            backend = self._core_cls.backend_for(
                outer,
                # No class serves the outer's scheme (not in `schemesmap`, or
                # unknown): it must not borrow a handle another path opened.
                shared=type(outer) is not URIPath,
                # A nested archive is named by its URI: asking it for its node
                # would settle its format.
                identity=outer.as_uri() if isinstance(outer, ArchiveURIPath) else None,
            )
        else:
            # A derived instance: the backend is known and `path` is already the inner path.
            # Member names never start with "/", but the generic `_make_child_relpath` joins
            # a child of the root as "/name".
            inner = path.lstrip("/")
        kwargs["backend"] = backend
        super()._init(source, inner, query, fragment, **kwargs)

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls, *args, **kwargs)
        if len(args) == 1 and isinstance(args[0], str) and not inst._raw_uris:
            # Keep the undecoded string for `_init` (see `_parse_archive_uri`).
            inst._raw_uris = [args[0]]
        return inst

    def _make_core(self):
        return self._core_cls(self.path, archive=super().backend)

    def refresh(self) -> None:
        """Forgets what is held of the archive's outer file, so the next use
        reads it again. A non-local archive is read once and kept while any
        path to it lives, so this is how a later change at its source is
        seen; a local one is checked against the file on every use. Every
        path to the same archive shares the refresh."""
        self._core_path.refresh()

    def batch(self) -> "_ty.ContextManager[None]":
        """A context manager that holds every change made to this archive
        while it is open and writes them in one replacement of the archive
        file when the outermost block ends without an exception; an exception
        leaves the archive as it was. Inside it every path of the archive
        reads the held changes, and the file is not touched until the block
        ends. A block inside another joins it. `NotImplementedError` when the
        archive cannot be written."""
        with self._delegated():
            return self._core_path.batch()

    def readlink(self) -> LinkTarget:
        """The text a link member stores, as a `LinkTarget` (`OSError(EINVAL)`
        when this member is not a link). Links on the way to it are followed."""
        with self._delegated():
            return self._core_path.readlink()

    @property
    def backend(self):
        return self._core_path.backend

    def _outer_path(self) -> "URIPath":
        """The archive's own path. Never decides the format."""
        return super().backend.outer

    def as_uri(self, /, sanitize=False):
        if not self.source:
            # A derived relative path (`relative_to`): no archive to name.
            return super().as_uri(sanitize=sanitize)
        # Encoded so the string parses back to the same member: the inner
        # path's `%`, `?` and `#`, and a literal "!/" inside the outer URI.
        outer = self._outer_path()
        outer_uri = outer.as_uri(sanitize=sanitize)
        if not isinstance(outer, ArchiveURIPath):
            # A nested archive's outer keeps its own separator (it already
            # encodes any other "!/"); see `_split_archive_path`.
            outer_uri = outer_uri.replace(_SEP, "%21/")
        # The composer's own encoding: a name that is not UTF-8 (a tar member
        # written in another charset) keeps its bytes as `%XX`.
        inner = percent_encode(self.path, SAFE_PATH)
        # A "!/" inside a member name must never read as a separator once
        # this URI is itself the outer of a nested archive.
        inner = inner.replace(_SEP, "%21/")
        tail = self._format_parsed_parts(
            Source(None, None, None, None), "", self.query, self.fragment
        )
        return f"{self.source.scheme}:{outer_uri}{_SEP}{inner}{tail}"

    def rm(
        self,
        /,
        recursive=False,
        missing_ok=False,
        ignore_error: "bool | _ty.Callable[[Exception, _ty.Self], bool]" = False,
        *,
        follow_symlinks=False,
        follow_binds=False,
    ):
        # An archive holds no bindings, and a link member is an entry like
        # any other for a removal that does not follow it.
        check_follow("follow_symlinks", follow_symlinks)
        check_follow("follow_binds", follow_binds)
        if not (
            recursive
            and self._rm_tree(
                as_error_handler(ignore_error), follows=follow_symlinks is not False
            )
        ):
            return super().rm(
                recursive=recursive,
                missing_ok=missing_ok,
                ignore_error=ignore_error,
                follow_symlinks=follow_symlinks,
                follow_binds=follow_binds,
            )

    def _rm_tree(self, on_error, follows: bool = False) -> bool:
        """The one-rewrite removal of a directory of a writable archive; False
        when it is not that case. `on_error` is asked about a failure with this
        path."""
        with self._delegated():
            return self._core_path._rm_tree(
                lambda error, _path: on_error(error, self), follows
            )

    def _same_filesystem(self, other) -> bool:
        # The archive handle is the namespace. An `archive:` path holds a
        # stand-in until its format is settled, and two of them naming one
        # archive settle on one handle.
        if isinstance(other, ArchiveURIPath):
            try:
                return other.backend is self.backend
            except Exception:
                # The archive cannot be read: nothing settles its handle.
                return False
        return super()._same_filesystem(other)

    def _same_location(self, other: URI) -> bool:
        # Every archive URI has the same bare "zip:"/"tar:" authority, so the
        # authority alone cannot tell two archives apart: an archive path is
        # only renameable onto a member of the very same archive (backend).
        if isinstance(other, ArchiveURIPath):
            return other.backend is self.backend
        if isinstance(other, URIPath):
            return False
        return super()._same_location(other)

    def rename(self, target: "ArchiveURIPath | URI | str"):
        # A plain str target is a sibling rename (relative to self's parent), as in sftp
        # and ftp. An existing target is replaced as POSIX rename(2) does (a file over a
        # file, a directory over an empty one), never a duplicate member. Returns the new path.
        target = self._rename_target(target)
        core = self._core_path
        moved = core.with_segments(target.path.lstrip("/"))
        destination = self._from_parsed_parts(
            self.source, target.path.lstrip("/"), "", ""
        )
        with self._delegated((str(moved), str(destination))):
            renamed = core.rename(moved)
        return self._from_parsed_parts(
            self.source, renamed.as_posix().lstrip("/"), "", ""
        )


class ZipURIPath(ArchiveURIPath):
    """`zip:` scheme (`archive+zip:` is a second name for it). Read/write: write support (new entries, overwriting
    existing entries, `unlink`/`rmdir`/`rename`) works when the outer
    archive is a local `file:` URI; every other outer scheme is read-only
    (fetched fully into memory first). Every mutation replaces the archive
    atomically (temp file + `os.replace`), so the result is a new file: other
    hard links keep the old content, and an archive the caller may not write
    is refused first. A new entry is appended, deflated, to a byte copy of the
    archive (nothing recompressed); overwriting/deleting/renaming an existing
    entry rewrites the whole archive, since the standard library's zip module has no in-place
    entry mutation, keeping every other entry's metadata and compression method.
    The members are read and written by a `pathlib_next.archive.ZipPath`."""

    __SCHEMES = ("zip", "archive+zip")
    __slots__ = ()
    _core_cls = ZipPath


class TarURIPath(ArchiveURIPath):
    """`tar:` scheme (also handles `.tar.gz`/`.tar.bz2`/`.tar.xz` via
    the standard library's auto-detected "r:*" mode). Read-only. Members stored with a
    `./` prefix are addressed without it. `archive+tar:` is the same scheme
    under a second name. The members are read by a
    `pathlib_next.archive.TarPath`."""

    __SCHEMES = ("tar", "archive+tar")
    __slots__ = ()
    _core_cls = TarPath


# `archive+zip:` and `archive+tar:` are second scheme names of `ZipURIPath` and
# `TarURIPath` (they pin the format, which the extension-detecting `archive:`
# does not); these class names stay importable.
ArchiveZipURIPath = ZipURIPath
ArchiveTarURIPath = TarURIPath
