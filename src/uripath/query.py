from __future__ import annotations

import collections.abc as _abc
import typing as _ty

import uritools as _uritools

from .source import ERRORS

if _ty.TYPE_CHECKING:
    from typing import TypeAlias
else:
    TypeAlias = _ty.Any

__all__ = ["Query", "QueryLike"]

# The reserved/safe set of uritools' own query helpers (private there), written
# against its public uriencode() so it does not depend on those internals.
_SAFE_QUERY = "!$&'()*+,;=:@/?"


def _querylist(
    items: _ty.Sequence[_ty.Tuple[str, _ty.Any]], sep: str, encoding: str
) -> bytes:
    # Escaped in every name and value: the separator; "=", which ends a name
    # ({"a=b": "c"} would decode as ("a", "b=c")); and "+", which a form-urlencoded
    # reader takes for a space (a base64 signature or "+00:00" would arrive altered).
    safe = _SAFE_QUERY.replace(sep, "").replace("=", "").replace("+", "")
    name_safe = safe
    terms = []
    for key, value in items:
        name = _uritools.uriencode(key, name_safe, encoding)
        if value is None:
            terms.append(name)
        elif isinstance(value, (bytes, str)):
            terms.append(name + b"=" + _uritools.uriencode(value, safe, encoding))
        else:
            terms.append(name + b"=" + _uritools.uriencode(str(value), safe, encoding))
    return sep.encode("ascii").join(terms)


def _querydict(mapping: _ty.Mapping[str, _ty.Any], sep: str, encoding: str) -> bytes:
    items = []
    for key, value in mapping.items():
        if isinstance(value, (bytes, str)):
            items.append((key, value))
        elif isinstance(value, _abc.Iterable):
            items.extend((key, v) for v in value)
        else:
            items.append((key, value))
    return _querylist(items, sep, encoding)


class Query:
    """A URI query as an immutable value: the percent-encoded text and the
    `(name, value)` pairs it stands for.

    Build one from pairs or a mapping (a sequence value repeats the name, a
    `None` value is a bare name) with `Query(...)`, which encodes them so that
    `to_pairs()` returns what was given, or from text with `Query.parse()`,
    which keeps the text byte for byte: it is what `URI.query` holds, as
    received, and what is sent. `str(query)` is that text.

    Two queries are equal, and hash alike, when they decode to the same pairs,
    whatever their spelling (`a=%41` and `a=A`); a query is never equal to a
    `str`, and has no length, items or iteration. `to_pairs()` and `to_dict()`
    follow RFC 3986, not `application/x-www-form-urlencoded`: only `%XX`
    escapes are decoded and a `+` stays a plus (`urllib.parse.parse_qsl` reads
    form text), and an escape that is not valid in `encoding` survives as a
    surrogate escape instead of raising.

    `separator` splits the text into terms (default `&`) and `encoding` is the
    charset of the escapes (default `utf-8`); both say how the text is read
    and are not part of the value."""

    __slots__ = ("_text", "_separator", "_encoding", "_pairs")
    SEPARATOR = "&"
    ENCODING = "utf-8"

    def __init__(
        self,
        pairs: (
            _ty.Mapping[str, str | None | _ty.Sequence[str | None]]
            | _ty.Sequence[tuple[str, str | None]]
            | Query
        ) = (),
        *,
        separator: str | None = None,
        encoding: str | None = None,
    ):
        if isinstance(pairs, (str, bytes)):
            raise TypeError(
                "a Query is built from pairs or a mapping; "
                "use Query.parse() for query text"
            )
        text = None
        if isinstance(pairs, Query):
            separator = separator or pairs._separator
            encoding = encoding or pairs._encoding
            if separator == pairs._separator and encoding == pairs._encoding:
                text = pairs._text
            else:
                pairs = pairs.to_pairs()
        else:
            separator = separator or self.SEPARATOR
            encoding = encoding or self.ENCODING
        if text is None:
            if isinstance(pairs, _abc.Mapping):
                text = _querydict(pairs, separator, encoding).decode()
            else:
                text = _querylist(pairs, separator, encoding).decode()
        self._set(text, separator, encoding)

    def _set(self, text: str, separator: str, encoding: str) -> None:
        object.__setattr__(self, "_text", text)
        object.__setattr__(self, "_separator", separator)
        object.__setattr__(self, "_encoding", encoding)
        object.__setattr__(self, "_pairs", None)

    @classmethod
    def parse(
        cls, text: str, *, separator: str = SEPARATOR, encoding: str = ENCODING
    ) -> Query:
        """The query that `text` spells, percent-encoded as received and kept
        byte for byte. Any text parses; `TypeError` for what is not a `str`."""
        if not isinstance(text, str):
            raise TypeError(f"query text must be a str, not {type(text).__name__!r}")
        query = object.__new__(cls)
        query._set(text, separator, encoding)
        return query

    @property
    def separator(self) -> str:
        """What splits the text into terms."""
        return self._separator

    @property
    def encoding(self) -> str:
        """The charset the escapes of the text are read in."""
        return self._encoding

    def to_pairs(self) -> list[tuple[str, str | None]]:
        """The decoded `(name, value)` pairs in order; `value` is `None` for a
        name with no `=`."""
        return list(self._decoded())

    def to_dict(self, *, single: bool = False):
        """The pairs by name: each name maps to the list of its values, or with
        `single` to its last value."""
        query_: dict[str, list[str | None]] = {}
        for k, v in self._decoded():
            if single:
                query_[k] = v
            else:
                query_.setdefault(k, []).append(v)
        return query_

    def _decoded(self) -> "tuple[tuple[str, str | None], ...]":
        pairs = self._pairs
        if pairs is None:
            found = []
            for term in self._text.split(self._separator):
                if not term:
                    continue
                name, equals, value = term.partition("=")
                found.append(
                    (
                        _uritools.uridecode(name, self._encoding, ERRORS),
                        (
                            _uritools.uridecode(value, self._encoding, ERRORS)
                            if equals
                            else None
                        ),
                    )
                )
            pairs = tuple(found)
            object.__setattr__(self, "_pairs", pairs)
        return pairs

    def __str__(self) -> str:
        return self._text

    def __repr__(self) -> str:
        extra = ""
        if self._separator != self.SEPARATOR:
            extra += f", separator={self._separator!r}"
        if self._encoding != self.ENCODING:
            extra += f", encoding={self._encoding!r}"
        return f"{type(self).__name__}.parse({self._text!r}{extra})"

    def __bool__(self) -> bool:
        return bool(self._text)

    def __eq__(self, other: object):
        if not isinstance(other, Query):
            return NotImplemented
        return self._decoded() == other._decoded()

    def __hash__(self) -> int:
        return hash(self._decoded())

    def __setattr__(self, name, value):
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, name):
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __reduce__(self):
        return (_rebuild, (self._text, self._separator, self._encoding))

    def __copy__(self) -> Query:
        return self

    def __deepcopy__(self, memo) -> Query:
        return self


def _rebuild(text: str, separator: str, encoding: str) -> Query:
    return Query.parse(text, separator=separator, encoding=encoding)


QueryLike: TypeAlias = (
    "str | Query | _ty.Mapping[str, str | None | _ty.Sequence[str | None]]"
    " | _ty.Sequence[tuple[str, str | None]]"
)
"""What `URI.with_query()` accepts in place of a `Query`: query text (taken as
already percent-encoded), a mapping or a sequence of pairs, or a `Query`; `None`
removes the query."""


def _coerce(query: "QueryLike | None") -> Query:
    """`query` as a `Query`: text is parsed, pairs and mappings are encoded,
    and `None` is the empty query."""
    if isinstance(query, Query):
        return query
    if query is None:
        return Query.parse("")
    if isinstance(query, str):
        return Query.parse(query)
    return Query(query)
