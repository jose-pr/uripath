from __future__ import annotations

import html.parser as _html_parser
import re as _re
import time as _time
import typing as _ty
import urllib.parse as _urlparse

_RE_ISO8601 = _re.compile(r"\d{4}-\d+-\d+T\d+:\d{2}:\d{2}Z")
_DATETIME_FMTs = (
    (_re.compile(r"\d+-[A-S][a-y]{2}-\d{4} \d+:\d{2}:\d{2}"), "%d-%b-%Y %H:%M:%S"),
    (_re.compile(r"\d+-[A-S][a-y]{2}-\d{4} \d+:\d{2}"), "%d-%b-%Y %H:%M"),
    (_re.compile(r"\d{4}-\d+-\d+ \d+:\d{2}:\d{2}"), "%Y-%m-%d %H:%M:%S"),
    (_RE_ISO8601, "%Y-%m-%dT%H:%M:%SZ"),
    (_re.compile(r"\d{4}-\d+-\d+ \d+:\d{2}"), "%Y-%m-%d %H:%M"),
    (_re.compile(r"\d{4}-[A-S][a-y]{2}-\d+ \d+:\d{2}:\d{2}"), "%Y-%b-%d %H:%M:%S"),
    (_re.compile(r"\d{4}-[A-S][a-y]{2}-\d+ \d+:\d{2}"), "%Y-%b-%d %H:%M"),
    (
        _re.compile(r"[F-W][a-u]{2} [A-S][a-y]{2} +\d+ \d{2}:\d{2}:\d{2} \d{4}"),
        "%a %b %d %H:%M:%S %Y",
    ),
    (
        _re.compile(r"[F-W][a-u]{2}, \d+ [A-S][a-y]{2} \d{4} \d{2}:\d{2}:\d{2} \S+"),
        "%a, %d %b %Y %H:%M:%S %Z",
    ),
    (_re.compile(r"\d{4}-\d+-\d+"), "%Y-%m-%d"),
    (_re.compile(r"\d+/\d+/\d{4} \d{2}:\d{2}:\d{2} [+-]\d{4}"), "%d/%m/%Y %H:%M:%S %z"),
    (_re.compile(r"\d{2} [A-S][a-y]{2} \d{4}"), "%d %b %Y"),
)


_RE_FILESIZE = _re.compile(r"\d[\d,]*(\.\d+)? ?[BKMGTPEZY]|\d[\d,]*|-", _re.I)
_RE_COMMONHEAD = _re.compile(
    "Name|(Last )?modifi(ed|cation)|date|Size|Description|Metadata|Type|Parent Directory",
    _re.I,
)
_RE_HEAD_NAME = _re.compile("name$|^file|^download")
_RE_HEAD_MOD = _re.compile("modifi|^uploaded|date|time")
_RE_HEAD_SIZE = _re.compile("size|bytes$")


def _human2bytes(s):
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        symbols = "BKMGTPEZY"
        letter = s[-1:].strip().upper()
        num = float(s[:-1])
        prefix = {symbols[0]: 1}
        for i, sym in enumerate(symbols[1:]):
            prefix[sym] = 1 << (i + 1) * 10
        return int(num * prefix.get(letter, 1))


def _aherf2filename(a_href):
    isdir = "/" if a_href.endswith("/") else ""
    path = _urlparse.urlsplit(a_href).path
    # The URI layer's handler: a name that is not UTF-8 (`caf%E9`) keeps its
    # bytes, so the child's request names the file the server listed.
    name = _urlparse.unquote(path.rstrip("/"), errors="surrogateescape")
    return name.rsplit("/", 1)[-1] + isdir


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(split: _urlparse.SplitResult) -> "tuple[str, str, int | None]":
    scheme = split.scheme.lower()
    try:
        port = split.port
    except ValueError:
        port = -1
    # `hostname` is lower case already; a host name is case-insensitive.
    return scheme, (split.hostname or "").lower(), port or _DEFAULT_PORTS.get(scheme)


class _FileEntry(_ty.NamedTuple):
    name: str
    modified: _ty.Optional[_time.struct_time]
    size: _ty.Optional[int]
    description: _ty.Optional[str]
    # False when `size` came from a human-readable column ("1.2K"): the
    # value is approximate and must not be reported as `st_size`.
    size_exact: bool = True


def _is_exact_size(sizestr: str) -> bool:
    sizestr = sizestr.replace(" ", "").replace(",", "")
    if sizestr[-1:] in ("b", "B"):
        sizestr = sizestr[:-1]
    return sizestr.isdigit()


class _DirectoryListingParser(_html_parser.HTMLParser):
    """Scrapes an HTML directory index into `_FileEntry`s.

    `base_url` is the URL the listing was fetched from (after redirects).
    When given, an entry is kept only if its href, resolved against that URL
    as a browser resolves it, names a direct child of the listed directory
    on the same origin -- so a page's links elsewhere, and a reverse proxy
    whose `<title>` names a different path than the request, are handled.
    Without it, absolute hrefs are scoped by the "Index of ..." title."""

    def __init__(self, base_url: "str | None" = None):
        super().__init__()
        self.listing = []
        self.base_url = base_url
        self._base_origin = None
        self._base_segments = None
        if base_url:
            split = _urlparse.urlsplit(base_url)
            self._base_origin = _origin(split)
            self._base_segments = [
                _urlparse.unquote(segment)
                for segment in split.path.rstrip("/").split("/")
            ]

        self.in_title = False
        self.in_pre = False
        self.in_table = False
        self.in_tr = False
        self.in_td = False
        self.in_a = False

        self.title_text = ""
        self.cwd = None

        self.table_rows = []
        self.current_row = []
        self.current_cell_text = []
        self.current_cell_href = None
        self.headers = None

        self.last_href = None
        self.pre_collect_data = False
        self.pre_data_buffer = []

        self.all_links = []
        self.current_a_href = None
        self.current_a_text = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
            self.title_text = ""
        elif tag == "pre":
            self.in_pre = True
        elif tag == "table":
            self.in_table = True
            self.table_rows = []
            self.headers = None
        elif tag == "tr" and self.in_table:
            self.in_tr = True
            self.current_row = []
        elif (tag == "td" or tag == "th") and self.in_tr:
            self.in_td = True
            self.current_cell_text = []
            self.current_cell_href = None
        elif tag == "a":
            self.in_a = True
            href = attrs_dict.get("href")
            if href:
                self.current_a_href = href
                self.current_a_text = []
                if self.in_td:
                    self.current_cell_href = href
                elif self.in_pre:
                    self._flush_pre_entry()
                    self.last_href = href
                    self.pre_collect_data = False

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
            title = self.title_text.strip()
            if title.startswith("Index of "):
                self.cwd = title[9:]
        elif tag == "pre":
            self._flush_pre_entry()
            self.in_pre = False
        elif tag == "table":
            self.in_table = False
            self._process_table()
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            self.table_rows.append(self.current_row)
        elif (tag == "td" or tag == "th") and self.in_td:
            self.in_td = False
            cell_text = "".join(self.current_cell_text).strip()
            self.current_row.append((cell_text, self.current_cell_href))
        elif tag == "a":
            self.in_a = False
            if self.current_a_href:
                text = "".join(self.current_a_text).strip()
                self.all_links.append((text, self.current_a_href))
                self.current_a_href = None
            if self.in_pre and self.last_href:
                self.pre_data_buffer = []
                self.pre_collect_data = True

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        elif self.in_td:
            self.current_cell_text.append(data)
        elif self.in_pre and self.pre_collect_data:
            self.pre_data_buffer.append(data)
        if self.in_a:
            self.current_a_text.append(data)

    def _is_child_href(self, href) -> bool:
        """Whether `href`, resolved against `base_url`, is a direct child of
        the listed directory on the same scheme, host and port."""
        split = _urlparse.urlsplit(_urlparse.urljoin(self.base_url, href))
        if _origin(split) != self._base_origin:
            return False
        segments = [
            _urlparse.unquote(segment) for segment in split.path.rstrip("/").split("/")
        ]
        base = self._base_segments
        return (
            len(segments) == len(base) + 1
            and segments[:-1] == base
            and segments[-1] != ""
        )

    def _is_ancestor_href(self, href):
        # With a `base_url`, anything but a direct child is skipped: the parent link is
        # not always "../" (it may be the absolute "/files/"), yet a server that renders
        # every entry as an absolute href must keep its listing, so the filter is scoped.
        if self.base_url:
            return not self._is_child_href(href)
        if not href.startswith("/"):
            return False
        if not self.cwd:
            return True
        path = _urlparse.unquote(_urlparse.urlsplit(href).path)
        cwd = self.cwd if self.cwd.endswith("/") else self.cwd + "/"
        # a strict descendant of cwd is a real child; cwd itself (a
        # self-referencing "up" link, e.g. at the site root) or anything
        # outside cwd is the ancestor/parent link.
        return path == cwd or not path.startswith(cwd)

    def _flush_pre_entry(self):
        if not self.last_href:
            return

        name = _aherf2filename(self.last_href)
        if (
            name in ("Parent Directory", "..", "../")
            or self.last_href.startswith("?")
            or self._is_ancestor_href(self.last_href)
        ):
            self.last_href = None
            return

        modified = None
        size = None
        size_exact = True
        description = None

        text = (
            "".join(self.pre_data_buffer).replace("\r", "").split("\n", 1)[0].lstrip()
        )
        if text:
            for regex, fmt in _DATETIME_FMTs:
                match = regex.match(text)
                if match:
                    try:
                        modified = _time.strptime(match.group(0), fmt)
                    except ValueError:
                        pass
                    text = text[match.end() :].lstrip()
                    break

            match = _RE_FILESIZE.match(text)
            if match:
                sizestr = match.group(0)
                if sizestr != "-":
                    size = _human2bytes(sizestr.replace(" ", "").replace(",", ""))
                    size_exact = _is_exact_size(sizestr)
                text = text[match.end() :].lstrip()

            if text:
                description = text.rstrip()
                if description == "/":
                    name += "/"
                    description = None

        self.listing.append(_FileEntry(name, modified, size, description, size_exact))
        self.last_href = None

    def _process_table(self):
        started = False
        for row in self.table_rows:
            has_head = False
            cell_texts = [cell[0] for cell in row]
            for text in cell_texts:
                if _RE_COMMONHEAD.search(text):
                    has_head = True
                    break

            if has_head and not started:
                self.headers = []
                name_found = False
                for text in cell_texts:
                    norm = text.strip(" \t\n\r\x0b\x0c\xa0↑↓").lower()
                    if not norm:
                        continue
                    if not name_found and _RE_HEAD_NAME.search(norm):
                        self.headers.append("name")
                        name_found = True
                    elif norm in ("size", "description"):
                        self.headers.append(norm)
                    elif _RE_HEAD_MOD.search(norm):
                        self.headers.append("modified")
                    elif _RE_HEAD_SIZE.search(norm):
                        self.headers.append("size")
                    elif norm.endswith("signature"):
                        self.headers.append("signature")
                    else:
                        self.headers.append("description")
                if not self.headers:
                    self.headers = ["name", "modified", "size", "description"]
                elif not name_found:
                    self.headers[0] = "name"
                started = True
                continue

            if started:
                file_name = None
                file_mod = None
                file_size = None
                file_size_exact = True
                file_desc = None

                status = 0
                for cell_text, cell_href in row:
                    if status >= len(self.headers):
                        break

                    header = self.headers[status]
                    if header == "name":
                        if not cell_href or cell_href.startswith("#"):
                            continue
                        name_val = cell_text.strip()
                        if name_val == "Parent Directory" or cell_href == "../":
                            break
                        if self.base_url and not self._is_child_href(cell_href):
                            break
                        file_name = _aherf2filename(cell_href)
                        status = 1
                    elif header == "modified":
                        timestr = cell_text.strip()
                        if timestr:
                            for regex, fmt in _DATETIME_FMTs:
                                match = regex.match(timestr)
                                if match:
                                    try:
                                        file_mod = _time.strptime(match.group(0), fmt)
                                    except ValueError:
                                        pass
                                    break
                        status += 1
                    elif header == "size":
                        sizestr = cell_text.strip().replace(",", "")
                        if sizestr and sizestr != "-":
                            match = _RE_FILESIZE.match(sizestr)
                            if match:
                                file_size = _human2bytes(
                                    match.group(0).replace(" ", "")
                                )
                                file_size_exact = _is_exact_size(match.group(0))
                        status += 1
                    elif header == "description":
                        file_desc = cell_text or None
                        status += 1
                    else:
                        status += 1

                if file_name:
                    self.listing.append(
                        _FileEntry(
                            file_name, file_mod, file_size, file_desc, file_size_exact
                        )
                    )

    def close(self):
        super().close()
        self._flush_pre_entry()
        if not self.listing:
            for text, href in self.all_links:
                name = _aherf2filename(href)
                if (
                    name in ("Parent Directory", "..", "../")
                    or href.startswith("?")
                    or self._is_ancestor_href(href)
                ):
                    continue
                self.listing.append(_FileEntry(name, None, None, None))
