import os
from pathlib import PurePosixPath as PosixPath, PurePath as _PurePath, _ignore_error
import typing as _ty
import uritools
import stat as _stat
import shutil as _shutil

if _ty.TYPE_CHECKING:
    from typing import Self

from . import fs as _fs, utils as _utils
import ipaddress as _ip
import io as _io


_IPAddress = _ip.IPv4Address | _ip.IPv6Address
UriLike: _ty.TypeAlias = "str | PureUri | os.PathLike"


class UriSource(_ty.NamedTuple):
    scheme: str
    userinfo: str
    host: str | _IPAddress
    port: int

    def __bool__(self):
        if not self.scheme:
            return False
        return True

    def parsed_userinfo(self):
        parts = []
        if self.userinfo:
            parts = self.userinfo.split(":", maxsplit=1)
        parts = parts + ["", ""]
        return parts[0], parts[1]


_NOSOURCE = UriSource(None, None, None, None)

_U = _ty.TypeVar("_U", bound="PureUri")


class _UriPathParents(_ty.Sequence[_U]):
    """This object provides sequence-like access to the logical ancestors
    of a path.  Don't try to construct it yourself."""

    __slots__ = ("_path", "_parents")

    def __init__(self, path: _U):
        self._path = path
        self._parents = path.posixpath.parents

    def __len__(self):
        return len(self._parents)

    def __getitem__(self, idx: int | slice) -> tuple[_U] | _U:
        if isinstance(idx, slice):
            return tuple(self[i] for i in range(*idx.indices(len(self))))
        return self._path.with_path(self._parents[idx].as_posix())

    def __repr__(self):
        return "<{}.parents>".format(type(self._path).__name__)


class PureUri(object):

    __slots__ = (
        "_raw_uris",
        "_source",
        "_path",
        "_posixpath",
        "_query",
        "_fragment",
        "_uri",
    )

    def __new__(cls, *uris, **options):
        inst = object.__new__(cls)
        for cls in cls.__mro__:
            for slot in getattr(cls, "__slots__", ()):
                if not hasattr(inst, slot):
                    setattr(inst, slot, None)
        return inst

    def __init__(self, *uris: UriLike, **options):
        _uris: list[str | PureUri] = []
        for uri in uris:
            if isinstance(uri, PureUri):
                _uris.append(uri)
            elif isinstance(uri, _PurePath):
                if uri.is_absolute():
                    _uris.append(uritools.uriencode(uri.as_posix()).decode())
                else:
                    _uris.append(uri.as_uri())
            elif isinstance(uri, str):
                _uris.append(uri)
            elif isinstance(uri, bytes):
                _uris.append(uri.decode())
            else:
                try:
                    path = os.fspath(uri)
                except TypeError:
                    path = uri
                if not isinstance(path, str):
                    raise TypeError(
                        "argument should be a str or an os.PathLike "
                        "object where __fspath__ returns a str, "
                        f"not {type(path).__name__!r}"
                    )
                _uris.append(uritools.uriencode(path).decode())
        self._raw_uris = _uris

    def with_segments(self, *pathsegments):
        return type(self)(*pathsegments)

    @classmethod
    def _parse_uri(cls, uri: str) -> tuple[UriSource, str, str, str]:
        parsed = uritools.urisplit(uri)
        return (
            UriSource(
                parsed.getscheme(),
                parsed.getuserinfo(),
                parsed.gethost() or "",
                parsed.getport(),
            ),
            parsed.getpath(),
            parsed.getquery(),
            parsed.getfragment(),
        )

    def _load_parts(self):
        uris = self._raw_uris
        source = query = fragment = None
        paths = []

        for _uri in uris or [""]:
            src, path, query, fragment = (
                _uri.parts if isinstance(_uri, PureUri) else self._parse_uri(_uri)
            )
            if src:
                source = src
                paths = [path]
            else:
                paths.append(path)
        _path = ""
        for path in reversed(paths):
            if path.endswith("/"):
                _path = f"{path}{_path}"
            elif _path:
                _path = f"{path}/{_path}"
            else:
                _path = path
            if _path.startswith("/"):
                break

        self._init(source, _path, query, fragment)

    def _init(self, source: UriSource, path: str, query: str, fragment: str, **kwargs):
        self._source = source
        self._path = path
        self._query = query
        self._fragment = fragment

    def _from_parsed_parts(
        self, source: UriSource, path: str, query: str, fragment: str
    ):
        uri_str = self._format_parsed_parts(source, path, query, fragment)
        uri = self.with_segments(uri_str)
        uri._uri = uri_str or "."
        self._init(source, path, query, fragment)
        return uri

    @classmethod
    def _format_parsed_parts(
        cls,
        source: UriSource,
        path: str,
        query: str,
        fragment: str,
        /,
        sanitize=True,
    ) -> str:
        parts = {
            "path": path,
        }
        if query:
            parts["query"] = query
        if fragment:
            parts["fragment"] = fragment
        if source:
            source_ = source._asdict()
            if sanitize:
                source_["userinfo"] = (source_["userinfo"] or "").split(
                    ":", maxsplit=1
                )[0]
            parts.update(source_)

        return uritools.uricompose(**{k: v for k, v in parts.items() if v})

    def __str__(self):
        """Return the string representation of the path, suitable for
        passing to system calls."""
        return self.as_uri()

    def __fspath__(self):
        return self.path

    def __repr__(self):
        return "{}({!r})".format(type(self).__name__, self.as_uri())

    def as_uri(self, /, sanitize=True):
        if self._uri is None or not sanitize:
            uri = self._format_parsed_parts(
                self.source, self.path, self.query, self.fragment, sanitize=sanitize
            )
            if sanitize:
                self._uri = uri
            return uri
        else:
            return self._uri

    @property
    def source(self) -> UriSource:
        if self._source is None:
            self._load_parts()
        return self._source

    @property
    def path(self) -> str:
        if self._path is None:
            self._load_parts()
        return self._path

    @property
    def query(self) -> str:
        if self._query is None:
            self._load_parts()
        return self._query

    @property
    def fragment(self) -> str:
        if self._fragment is None:
            self._load_parts()
        return self._fragment

    @property
    def posixpath(self) -> PosixPath:
        if self._posixpath is None:
            self._posixpath = PosixPath(self.path)
        return self._posixpath

    @property
    def name(self):
        return self.posixpath.name

    @property
    def suffix(self):
        return self.posixpath.suffix

    @property
    def suffixes(self):
        return self.posixpath.suffixes

    @property
    def stem(self):
        return self.posixpath.stem

    def with_source(self, source: UriSource):
        return self._from_parsed_parts(source, self.path, self.query, self.fragment)

    def with_path(self, path: str | _PurePath):
        return self._from_parsed_parts(
            self.source,
            path.as_posix() if isinstance(path, _PurePath) else path,
            self.query,
            self.fragment,
        )

    def with_query(self, query: str):
        return self._from_parsed_parts(self.source, self.path, query, self.fragment)

    def with_fragment(self, fragment: str):
        return self._from_parsed_parts(self.source, self.path, self.query, fragment)

    def with_name(self, name: str):
        return self._from_parsed_parts(
            self.source,
            self.posixpath.with_name(name).as_posix(),
            self.query,
            self.fragment,
        )

    def with_stem(self, stem: str):
        return self.with_name(stem + self.suffix)

    def with_suffix(self, suffix: str):
        return self._from_parsed_parts(
            self.source,
            self.posixpath.with_suffix(suffix).as_posix(),
            self.query,
            self.fragment,
        )

    @property
    def parts(self):
        return self.source, self.path, self.query, self.fragment

    def joinpath(self, *pathsegments: UriLike):
        """Combine this path with one or several arguments, and return a
        new path representing either a subpath (if all arguments are relative
        paths) or a totally different path (if one of the arguments is
        anchored).
        """
        return self.with_segments(self, *pathsegments)

    def __truediv__(self, key: UriLike):
        try:
            return self.joinpath(key)
        except TypeError:
            return NotImplemented

    def __rtruediv__(self, key: UriLike):
        try:
            return self.with_segments(key, self)
        except TypeError:
            return NotImplemented

    @property
    def parent(self):
        """The logical parent of the path."""
        parent = self.posixpath.parent
        if parent == self.posixpath:
            return self
        return self.with_path(parent.as_posix())

    @property
    def parents(self):
        return _UriPathParents(self)

    def is_absolute(self):
        """True if the path is absolute (has both a root and, if applicable,
        a drive)."""
        return bool(self.source) and self.posixpath.is_absolute()

    def is_relative_to(self, other: UriLike):
        """Return True if the path is relative to another path or False."""
        other = self.with_segments(other)
        return other == self or other in self.parents

    def relative_to(self, other: UriLike, /, walk_up=False):
        other = self.with_segments(other)
        if (self.source and other.source) and other.source != self.source:
            raise ValueError(f"{str(self)!r} is not in the subpath of {str(other)!r}")
        try:
            relpath = self.posixpath.relative_to(other.path, walk_up)
        except ValueError:
            relpath = self.posixpath
        return self._from_parsed_parts(
            _NOSOURCE, relpath.as_posix(), self.query, self.fragment
        )


class Uri(PureUri):
    __slots__ = ("_backend",)
    _SCHEMES_: list[str] = []

    def __new__(cls, *args, **kwargs):
        if cls is Uri:
            uri = PureUri(*args, **kwargs)
            if uri.source and uri.source.scheme:
                for scls in Uri.__subclasses__():
                    if uri.source.scheme in scls._SCHEMES_:
                        cls = scls
                        break
        inst = PureUri.__new__(cls, *args, **kwargs)
        inst._backend = kwargs.get("backend", None)
        return inst

    def _initbackend(self):
        return None

    @property
    def backend(self):
        if self._backend is None:
            self._backend = self._initbackend()
        return self._backend

    def with_backend(self, backend):
        uri = self._from_parsed_parts(*self.parts)
        uri._backend = backend
        return uri

    def with_segments(self, *pathsegments):
        r = super().with_segments(*pathsegments)
        backend = None
        for p in reversed(pathsegments):
            if isinstance(p, type(r)) and p._backend is not None:
                backend = p._backend
                break
        r._backend = backend
        return r

    @_utils.notimplemented
    def _ls(self) -> "_ty.Iterable[str]": ...

    def iterdir(self) -> "_ty.Iterable[Self]":
        for path in self._ls():
            inst = type(self).__new__(self.__class__, backend=self.backend)
            inst._init(self.source, f"{self.path}/{path}", "", "")
            yield inst

    @_utils.notimplemented
    def stat(self) -> _fs.FileStat: ...

    def is_dir(self):
        """
        Whether this path is a directory.
        """
        try:
            return _stat.S_ISDIR(self.stat().st_mode)
        except OSError as e:
            if not _ignore_error(e):
                raise
            return False
        except ValueError:
            return False

    def is_file(self):
        """
        Whether this path is a regular file (also True for symlinks pointing
        to regular files).
        """
        try:
            return _stat.S_ISREG(self.stat().st_mode)
        except OSError as e:
            if not _ignore_error(e):
                raise
            return False
        except ValueError:
            return False

    @_utils.notimplemented
    def _open(
        self,
        mode="r",
        buffering=-1,
    ) -> _io.IOBase:
        """
        All operations should be binary
        To be used only by UriPath.open() to obtain binary stream
        """
        ...

    def open(
        self, mode="r", buffering=-1, encoding=None, errors=None, newline=None
    ) -> _io.IOBase:
        fh = self._open(mode.replace("b", ""), buffering)
        if "b" not in mode:
            encoding = _io.text_encoding(encoding)
            fh = _io.TextIOWrapper(fh, encoding, errors, newline)
        return fh

    def read_bytes(self) -> bytes:
        """
        Open the file in bytes mode, read it, and close the file.
        """
        with self.open(mode="rb") as f:
            return f.read()

    def read_text(self, encoding: str = None, errors=None) -> str:
        with self.open(mode="r", encoding=encoding, errors=errors) as f:
            return f.read()

    def write_bytes(self, data: bytes):
        view = memoryview(data)
        with self.open(mode="wb") as f:
            return f.write(view)

    def write_text(self, data: str, encoding: str = None, errors=None, newline=None):
        if not isinstance(data, str):
            raise TypeError("data must be str, not %s" % type(data).__name__)
        encoding = _io.text_encoding(encoding)
        with self.open(
            mode="w", encoding=encoding, errors=errors, newline=newline
        ) as f:
            return f.write(data)

    def exists(self) -> bool:
        try:
            self.stat()
            return True
        except FileNotFoundError:
            return False

    def walk(self, top_down=True, on_error=None, follow_symlinks=False):
        """Walk the directory tree from this directory, similar to os.walk()."""
        paths: "list[Uri|tuple[Uri, list[str], list[str]]]" = [self]

        while paths:
            path = paths.pop()
            if isinstance(path, tuple):
                yield path
                continue
            try:
                scandir_it = path.iterdir()
            except OSError as error:
                if on_error is not None:
                    on_error(error)
                continue

            dirnames: "list[str]" = []
            filenames: "list[str]" = []
            for entry in scandir_it:
                try:
                    is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
                except OSError:
                    # Carried over from os.path.isdir().
                    is_dir = False

                if is_dir:
                    dirnames.append(entry.name)
                else:
                    filenames.append(entry.name)

            if top_down:
                yield path, dirnames, filenames
            else:
                paths.append((path, dirnames, filenames))

            paths += [path / d for d in reversed(dirnames)]

    @_utils.notimplemented
    def _mkdir(self, mode:int): ...

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        """
        Create a new directory at this given path.
        """
        try:
            self._mkdir(self, mode)
        except FileNotFoundError:
            if not parents or self.parent == self:
                raise
            self.parent.mkdir(parents=True, exist_ok=True)
            self.mkdir(mode, parents=False, exist_ok=exist_ok)
        except OSError:
            # Cannot rely on checking for EEXIST, since the operating system
            # could give priority to other errors like EACCES or EROFS
            if not exist_ok or not self.is_dir():
                raise

    @_utils.notimplemented
    def chmod(self, mode: int): ...

    @_utils.notimplemented
    def unlink(self, missing_ok=False): ...

    @_utils.notimplemented
    def rmdir(self): ...

    def rm(self, /, recursive=False, missing_ok=False, ignore_error=False):
        _onerror = lambda _err, _path: (
            ignore_error if not callable(ignore_error) else ignore_error
        )
        try:
            if not self.exists():
                if missing_ok:
                    return
                raise FileNotFoundError(self)
            if self.is_dir():
                if recursive:
                    for child in self.iterdir():
                        child.rm(recursive=recursive, ignore_error=ignore_error)
                self.rmdir()
            else:
                self.unlink()
        except Exception as error:
            if not _onerror(error, self):
                raise

    @_utils.notimplemented
    def _rename(self, target: PosixPath): ...

    def _src_dest(self, target: UriLike) -> "tuple[Uri,Uri]":
        target = Uri(target) if not isinstance(target, Uri) else target
        src = self
        if not src.source:
            if target.source:
                src = src.with_source(target.source)
            else:
                raise FileNotFoundError(src)

        if not target.source:
            target = target.with_source(self.source)

        if target.source == src.source and target.path == src.path:
            return None, None

        return src, target

    def copy(self, target: UriLike, *, overwrite=False):
        src, target = self._src_dest(target)
        if src is None:
            return

        if target.exists():
            if overwrite:
                target.unlink()
            else:
                raise FileExistsError(target)

        try:
            stat = src.stat()
        except NotImplementedError:
            stat = None

        with target.open("wb") as output, src.open("rb") as input:
            _shutil.copyfileobj(input, output)

        if stat:
            try:
                target.chmod(stat.st_mode)
            except NotImplementedError:
                pass

    def move(self, target: UriLike, *, overwrite=False):
        src, target = self._src_dest(target)
        if src is None:
            return

        if target.exists():
            if overwrite:
                target.unlink()
            else:
                raise FileExistsError(target)

        if target.source == src.source:
            try:
                return src._rename(target.posixpath)
            except NotImplementedError:
                pass

        src.copy(target)
        src.unlink()
