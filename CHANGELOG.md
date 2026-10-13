# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `uripath`, the URI layer of `pathlib-next` as its own distribution: `URI`,
  `URIPath`, `Source` and `Query`, the schemes `file:`, `data:`, `ftp:`, `ftps:`,
  `zip:`, `tar:`, `archive:`, `http:`, `https:`, `dav:`, `davs:`, `github:`,
  `gitlab:` and `git:`, and the `uripath` command. It depends on `pathlib-next`,
  `netimps` and `uritools`.
- `sftp:`, `s3:`, `gs:` and `az:` are known scheme names that this distribution
  does not implement. A path of one joins, compares and prints without the
  distribution that provides it; the first operation that needs the server
  (`stat()`, `open()`, `iterdir()`, `exists()`, ...) raises an `ImportError`
  naming what to install: `uripath-sftp[paramiko]` (or `[asyncssh]`) for
  `sftp:`, and `uripath-objstore[s3]`, `[gs]` or `[az]`. `URIPath.schemes()`
  lists the four, and `URIPath.scheme_class()` raises the same error for them.
  A distribution that registers one of these names in the `uripath.schemes`
  entry-point group takes it.
- `uripath.__version__`, read from the installed metadata.
- `FTPURIBackend` and `BaseFTPURIBackend` have `close()` and are context
  managers: `close()` closes the control connection every thread holds to the
  servers of that backend, may be called twice, and a later use connects
  again. Leaving a `with` block calls it.
- Building an `HTTPTransport` or an `FTPURIBackend` with `verify=False` and no
  `ssl_context` logs a warning on the `uripath` logger each time.

### Changed

- Import from `uripath` where the code imported from `pathlib_next.uri`.
  `pathlib_next.uri` and `pathlib_next.tools.uripath` are not in this
  distribution. The classes spell their acronyms in capitals, and the class of a
  scheme is named `<Scheme>URIPath`, so `<Scheme>Path` stays the class that needs
  no URI. A scheme's module is private: every public name of a scheme is
  exported by `uripath.schemes`. There is no alias for an old name or path:
  change the import. Everything that moved or was renamed is in this table.

  | Was (in `pathlib_next.uri`) | Is (in `uripath`) |
  | --- | --- |
  | `Uri`, `UriPath`, `UriLike` | `uripath.URI`, `URIPath`, `URILike` |
  | `source.Source` | `uripath.Source`, also `uripath.source.Source` |
  | `source.compose_uri`, `compose_host`, `percent_encode`, `is_drive`, `SAFE_PATH`, `ERRORS` | the same names in `uripath.source` |
  | `same_authority` | `uripath.source.same_authority` |
  | `DerivedBackend` | `uripath.schemes.DerivedBackend` |
  | `query.Query` | `uripath.Query`, also `uripath.query.Query`; no longer a `str` (see below) |
  | `Query(text)`, `Query.decode()` | `Query.parse(text)`, `Query.to_pairs()` |
  | `Source.from_str(text, strict)` | `Source.parse(text, *, strict=True)`, and `Source.try_parse(text, default=None, *, strict=True)` |
  | `Source.as_str(sanitize=True)` | `str(source)` |
  | `Source.as_str(sanitize=False)` | `Source.reveal()` |
  | `schemes.file.FileUri`, `schemes.data.DataUri` | `uripath.schemes.FileURIPath`, `DataURIPath` |
  | `schemes.archive.ZipUri`, `TarUri`, `ArchiveUri` | `uripath.schemes.ZipURIPath`, `TarURIPath`, `ArchiveURIPath` |
  | `schemes.archive.ArchiveZipUri`, `ArchiveTarUri` | `uripath.schemes.ArchiveZipURIPath`, `ArchiveTarURIPath` |
  | `schemes.ftp.FtpPath` | `uripath.schemes.FTPURIPath` |
  | `schemes.ftp.FtpBackend`, `BaseFtpBackend` | `uripath.schemes.FTPURIBackend`, `BaseFTPURIBackend` |
  | `schemes.ftp.DEFAULT_TIMEOUT`, `IDLE_PROBE_SECONDS`; `schemes.archive.MAX_LINKS`, `LinkTarget` | `pathlib_next.ftp` and `pathlib_next.archive`, which define them |
  | `schemes.http.HttpPath`, `HttpBackend` | `uripath.schemes.HTTPURIPath`, `HTTPBackend` |
  | `schemes.http.HttpWriteStream`, `HttpAppendStream` | `uripath.schemes.HTTPWriteStream`, `HTTPAppendStream` |
  | `schemes.http.HTTPTransport`, `HTTPResponse` | `uripath.schemes.HTTPTransport`, `HTTPResponse` |
  | `schemes.http.MAX_LISTING_BYTES` | `uripath.schemes.MAX_LISTING_BYTES` (assign it there) |
  | `schemes.http.DEFAULT_TIMEOUT` | none: the default is the `timeout=` of the backend, `(10, 60)` |
  | `schemes.archive._base.MEMBER_SPOOL_BYTES` | `uripath.schemes.MEMBER_SPOOL_BYTES` |
  | `schemes.dav.DavPath` | `uripath.schemes.DAVURIPath` |
  | `schemes.github.GitHubPath`, `RepoBackend`; `schemes._gitrepo.BaseRepoBackend` | `uripath.schemes.GitHubURIPath`, `RepoBackend`, `BaseRepoBackend` |
  | `schemes.gitlab.GitLabPath` | `uripath.schemes.GitLabURIPath` |
  | `schemes.git.GitPath`, `GitHubGitPath`, `GitLabGitPath` | `uripath.schemes.GitURIPath`, `GitHubGitURIPath`, `GitLabGitURIPath` |
  | `schemes.github.InsecureTransportWarning` (also in `schemes.gitlab`) | `uripath.exceptions.InsecureTransportWarning` |

  The `ftp:` backends are not `pathlib_next.ftp.FTPBackend` and `BaseFTPBackend`:
  those belong to one host, while `FTPURIBackend` connects to whichever server a
  path names.
- `Query` is an immutable value and no longer a subclass of `str`. Was: a `str`
  that also took pairs, so `len(query)`, `query[0]`, `"x" in query`,
  `query.split("&")` and `query == "a=1"` worked as on a string while iterating
  it gave decoded pairs; equality and hash were those of the text, so
  `Query("a=1;b=2", separator=";") == Query("a=1;b=2")`; `Query(query)` reset the
  separator; `Query("a=%E9").decode()` raised `UnicodeDecodeError`. Is: `str(query)`
  is the text, `Query.parse(text)` builds one from text (kept byte for byte, as
  `URI.query` holds it), `Query(pairs)` from a mapping or pairs, and
  `query.to_pairs()` and `query.to_dict()` give the pairs; two queries are equal
  when they decode to the same pairs, a query is equal to nothing that is not a
  query, and an escape that is not valid UTF-8 survives as a surrogate escape
  instead of raising. A query has no length, items or iteration. What to do:
  `Query("a=1")` becomes `Query.parse("a=1")` (it is a `TypeError` now),
  `query.decode()` becomes `query.to_pairs()`, `for pair in query` becomes
  `for pair in query.to_pairs()`, and a comparison of `uri.query` with text
  becomes `str(uri.query) == text`. `URI.query` is still a `Query` and
  `with_query()` still takes text, a mapping, pairs or a `Query`.
- `Source` follows the conversion names. Was: `Source.from_str(text, strict)`,
  `source.as_str(sanitize=True)` (the same text as `str(source)`) and
  `source.as_str(sanitize=False)` (the text with the password). Is:
  `Source.parse(text, *, strict=True)`, `Source.try_parse(text, default=None,
  *, strict=True)` (the default instead of the error, and still a `TypeError`
  for what is not text), `str(source)` (the canonical text, without the
  password) and `source.reveal()` (the text with the password, named as an
  action because it carries the secret). `strict` is keyword-only. There is no
  alias: replace the call. `Source` is still a named tuple, so positional
  construction and unpacking are unchanged.
- Text that is not a URI raises `URISyntaxError` where it raised a bare
  `ValueError`: a port outside 0-65535, a malformed host or IPv6 address,
  `Source.parse()` of text with a path, a `git:` URI on a host with no
  provider, a `zip:` URI without the scheme of its archive. It is a subclass of
  `ValueError`, so `except ValueError` still catches it. `URIPath.scheme_class()`
  of a scheme nobody registered raises `UnsupportedSchemeError`, also a
  `ValueError`. Both derive from `URIPathError`, which `uripath` exports with
  them; a caller's bad argument stays a plain `ValueError` or `TypeError`.
- The environment variable that chooses the default HTTP transport is
  `URIPATH_HTTP_TRANSPORT`. `PATHLIB_NEXT_HTTP_TRANSPORT` is not read: set the
  new one.
- Requests of `http:`, `dav:`, `github:` and `gitlab:` send
  `User-Agent: uripath/<version>` instead of `User-Agent: pathlib-next`; the
  version is `uripath.__version__`. A backend's `headers=` still replaces it.
- The entry-point group for third-party schemes is `uripath.schemes`. A plugin
  registered under `pathlib_next.schemes` is not found: register it under the
  new group.
- The `requests` HTTP transport is provided by `uripath-http-requests`.
  `HTTPURIPath.with_session()`, `RepoBackend(session=...)`, `RepoBackend(**requests_args)`
  and `URIPATH_HTTP_TRANSPORT=requests` raise an `ImportError` naming it;
  install it to use them. A proxy URL the built-in transport cannot use
  (`socks5:`, `https:`) names it in its error too.
- There are no extras. `uritools` and `netimps` are required dependencies, so
  `pip install uripath` is all that `pathlib-next[uri]` was; the `http`,
  `sftp`, `sftp-async`, `s3`, `gs` and `az` extras are the distributions named
  above.
