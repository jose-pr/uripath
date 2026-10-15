# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-14

Published on PyPI as `pathapi-uri` (`pip install pathapi-uri`); the import
package and the command are `uripath`.

The first release of `uripath`: the URI layer of `pathlib-next` 0.9.14
(`pathlib_next.uri` and the `uripath` command) as a distribution of its own. It
needs Python 3.9 or newer, `pathapi>=0.1.0,<0.2` and
`netimps>=0.4.0,<0.5`, and nothing else; its one extra, `cli`, adds the command
(`duho>=0.7.3,<0.8`). Every scheme it implements runs on the standard library.
Under *Changed*, the migration from `pathlib_next.uri` comes in this order: the
table of names, the table of extras, then every change of behaviour with what to
do about it.

It is built on `pathapi`, which was published as `pathlib-next` up to 0.10.0 (import
name `pathlib_next`); the old names below are the ones before the move.

### Added

- `URI`, `URIPath`, `Source` and `Query`, the schemes `file:`, `data:`, `ftp:`,
  `ftps:`, `zip:`, `tar:`, `archive:`, `http:`, `https:`, `dav:` and `davs:`,
  and the `uripath` command, with `uripath.__version__` (read from the
  installed metadata).
- `pathapi.protocols.supports()` and `capabilities()` tell the truth about a URI
  class: `data:` does not support `Listing`, a scheme that lists through `_listdir()`
  or its own `_scandir()` does, and an instance of a `DelegatingURIPath` scheme
  answers with its core path (`_supports()`), so a delegated hook the core path
  lacks reads as absent.
- `sftp:`, `s3:`, `gs:`, `az:`, `repo:`, `github:` and `gitlab:` are known
  scheme names that this distribution does not implement. A path of one joins,
  compares and prints without the distribution that provides it; the first
  operation that needs the server (`stat()`, `open()`, `iterdir()`,
  `exists()`, ...) raises an `ImportError` naming what to install:
  `sftppath[paramiko]` (or `[asyncssh]`) for `sftp:`, `objpath[s3]`, `[gs]` or
  `[az]`, and `repopath` for the other three. `URIPath.schemes()` lists the
  seven, and `URIPath.scheme_class()` raises the same error for them. The user
  slot of `repo:`, `github:` and `gitlab:` is an access token, so `str()` and
  `repr()` of a `Source` of those schemes show no userinfo.
  A distribution that registers one of these names in the `uripath.schemes`
  entry-point group takes it.
- `http:`, `https:`, `dav:` and `davs:` send through the
  HTTP client and transport of `pathapi.http`, which `uripath` does not
  copy: `HTTPTransport`, `HTTPResponse`, the transport contract, the rules for
  redirects and credentials, the cap on a reply read whole
  (`pathapi.http.MAX_REPLY_BYTES`), `PATHAPI_HTTP_TRANSPORT` and the
  entry-point group `pathapi.http_transports` all live there, and so does
  `python -m pathapi.http.testing --http-transports NAME`, the suite that a
  distribution providing a transport runs over it. `HTTPBackend` is a
  `pathapi.http.HTTPClient` that adds what a path needs.
- `uripath.exceptions`: `URIPathError`, the base of what this package raises
  on its own, with `URISyntaxError` and `UnsupportedSchemeError` (both also
  `ValueError`) and `OutputClosedError` (also `BrokenPipeError`).
- `uripath.schemes.DelegatingURIPath` is the base of a scheme whose I/O is
  done by a `pathapi.Path` that needs no URI, and the one `file:`, `ftp:`
  and the archive schemes use. A distribution that provides a scheme this way
  (the `sftp:` of `sftppath`) lists the hooks it hands over in `_DELEGATED` and
  builds the path in `_make_core()`; the header documents both under "For
  scheme implementers".
- `uripath.source.fold_host(host)` returns the form of a host that comparisons
  and caches key on.
- `DataURIPath.charset` is the charset a `data:` URI declares.
- `FTPURIBackend` and `BaseFTPURIBackend` have `close()` and are context
  managers: `close()` closes the control connection every thread holds to the
  servers of that backend, may be called twice, and a later use connects
  again. Leaving a `with` block calls it.
- Building an `FTPURIBackend` with `verify=False` and no `ssl_context` logs a
  warning on the `uripath` logger each time (an `HTTPTransport` does the same on
  the `pathapi` logger).
- `uripath.as_path(text)` returns the `URIPath` or `LocalPath` that command-line
  style text names (`C:/data`, `12:30.txt` and `notes:draft` are local paths;
  `ftp://h/x` and `data:,abc` are URIs), and `uripath.copy_stream(source,
  target)` copies the bytes of a path or a binary stream into another in chunks,
  with `exclusive=True` for an exclusive create. The `uripath` command is built
  on them. `copy_stream` raises `OutputClosedError` when the reader of a target
  stream went away.
- `python -m uripath` runs the command, and `uripath --version` prints the
  version. The command describes itself to an agent (`AGENT_HELP=1 uripath
  --help` prints one JSON document) and can be served as tools
  (`URIPATH_MCP=stdio uripath`): `read`, `write`, `rm`, `cp` and `sync`, with
  the schemas their fields give. A tool has no standard input, so `-` as a
  source and `write` without `DATA` fail with a message.

### Changed

- Import from `uripath` where the code imported from `pathlib_next.uri`. There
  is no alias for an old name or path: change the import. The classes spell
  their acronyms in capitals, and the class of a scheme is named
  `<Scheme>URIPath`, so `<Scheme>Path` stays the class that needs no URI. A
  scheme's module is private: every public name of a scheme is exported by
  `uripath.schemes`. Everything that was renamed or moved:

  | Was (in `pathlib_next.uri`, `pathlib_next` 0.9.14) | Is |
  | --- | --- |
  | the package `pathlib_next.uri` | `uripath` |
  | `Path`, `Pathname`, `FileStat` imported from `pathlib_next.uri` | the same names in `pathapi` |
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
  | the modules `schemes.file`, `data`, `dav`, `ftp`, `http`, `archive` | private; each public name is `uripath.schemes.<Name>` |
  | `schemes.file.FileUri`, `schemes.data.DataUri` | `uripath.schemes.FileURIPath`, `DataURIPath` |
  | `schemes.archive.ZipUri`, `TarUri`, `ArchiveUri` | `uripath.schemes.ZipURIPath`, `TarURIPath`, `ArchiveURIPath` |
  | `schemes.archive.ArchiveZipUri`, `ArchiveTarUri` | `uripath.schemes.ArchiveZipURIPath`, `ArchiveTarURIPath` |
  | `schemes.ftp.FtpPath` | `uripath.schemes.FTPURIPath` |
  | `schemes.ftp.FtpBackend`, `BaseFtpBackend` | `uripath.schemes.FTPURIBackend`, `BaseFTPURIBackend` |
  | `schemes.ftp.DEFAULT_TIMEOUT`, `IDLE_PROBE_SECONDS`; `schemes.archive.MAX_LINKS`, `LinkTarget` | `pathapi.ftp` and `pathapi.archive`, which define them |
  | `schemes.http.HttpPath`, `HttpBackend` | `uripath.schemes.HTTPURIPath`, `HTTPBackend` |
  | `schemes.http.HttpWriteStream`, `HttpAppendStream` | `uripath.schemes.HTTPWriteStream`, `HTTPAppendStream` |
  | `schemes.http.HTTPTransport`, `HTTPResponse` | `pathapi.http.HTTPTransport`, `HTTPResponse` |
  | `schemes.http.MAX_LISTING_BYTES` | `pathapi.http.MAX_REPLY_BYTES` (assign it there) |
  | `schemes.http.DEFAULT_TIMEOUT` | none: the default is the `timeout=` of the backend, `(10, 60)` |
  | `schemes.archive._base.MEMBER_SPOOL_BYTES` | `uripath.schemes.MEMBER_SPOOL_BYTES` |
  | `schemes.dav.DavPath` | `uripath.schemes.DAVURIPath` |
  | `schemes.github.GitHubPath`, `schemes.gitlab.GitLabPath`, `schemes.git.GitPath`, `GitHubGitPath`, `GitLabGitPath` | the distribution `repopath`: `repopath.uri.GitHubURIPath`, `GitLabURIPath` and `RepoURIPath` (the `repo:` scheme); `repopath.GitHubPath` and `GitLabPath` need no URI |
  | `schemes.github.RepoBackend`; `schemes._gitrepo.BaseRepoBackend` | `repopath.RepoBackend`, `BaseRepoBackend` |
  | `schemes.github.InsecureTransportWarning` (also in `schemes.gitlab`) | `repopath.InsecureTransportWarning` |
  | `schemes.sftp`, `schemes.s3`, `schemes.gs`, `schemes.az` and the classes in them | the distributions `sftppath` and `objpath`, which name their own classes |
  | `schemes.http.RequestsTransport` | the distribution `pathapi-requests` |
  | `pathlib_next.tools.uripath`: `main(argv, *, stdin, stdout, stderr)`, `build_parser()` | `uripath.cli.main(argv=None)`; no parser to build |
  | `PATHLIB_NEXT_SFTP_BACKEND` | `SFTPPATH_BACKEND`, read by `sftppath` |
  | the entry-point group `pathlib_next.schemes` | `uripath.schemes` |
  | the script `uripath = pathlib_next.tools.uripath:main` | `uripath = uripath.cli:main`, which needs the `cli` extra; `python -m uripath` runs it too |

  The `ftp:` backends are not `pathapi.ftp.FTPBackend` and `BaseFTPBackend`:
  those belong to one host, while `FTPURIBackend` connects to whichever server a
  path names.

- What to install where `pathlib-next` had an extra. `pathlib-next` 0.10 has no
  `uri`, `http`, `sftp`, `sftp-async`, `s3`, `gs` or `az` extra.

  | Was | Install now |
  | --- | --- |
  | `pathlib-next[uri]` | `uripath` |
  | `pathlib-next[http]` | `uripath`; add `pathapi-requests` only for a `requests.Session` or `PATHAPI_HTTP_TRANSPORT=requests` |
  | `pathlib-next[sftp]` | `sftppath[paramiko]` |
  | `pathlib-next[sftp-async]` | `sftppath[asyncssh]` |
  | `pathlib-next[s3]`, `[gs]`, `[az]` | `objpath[s3]`, `[gs]`, `[az]` |
  | the `uripath` command (part of `pathlib-next[uri]`) | `uripath[cli]` |

  The `github:` and `gitlab:` schemes of `pathlib-next[uri]` are in the
  distribution `repopath` (`pip install "repopath[uri]"`), together with
  `repo:`, which takes the place of `git:`. `git:`, `git+github:` and
  `git+gitlab:` do not exist any more: a URI of one of them is a path of an
  unknown scheme, which joins and prints and raises `NotImplementedError` for
  a request. Rewrite the URIs:

  | Was | Is now |
  | --- | --- |
  | `git://github.com/o/r/f`, `git://gitlab.com/o/r/f` | `repo://github.com/o/r/f`, `repo://gitlab.com/o/r/f` (the kind is detected from the host) |
  | `git+github://host/o/r/f` | `github://host/o/r/f` |
  | `git+gitlab://host/o/r/f` | `gitlab://host/o/r/f` |
  | `github://host/o/r/f`, `gitlab://host/o/r/f` | the same text, with `repopath[uri]` installed |

  `uritools` is no longer installed with the URI layer; `netimps` is a required
  dependency.

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
  action because it carries the secret). `strict` is keyword-only. What to do:
  replace the call. `Source` is still a named tuple, so positional
  construction and unpacking are unchanged.
- A join keeps the query and the fragment of the path it starts from. Was:
  `Uri("unk://h/d?sig=abc#frag") / "f"` and `joinpath("f")` gave
  `unk://h/d/f`, and so did the children `iterdir()`, `glob()` and `walk()`
  yield, while `parent`, `with_name()`, `with_stem()`, `with_suffix()` and
  `relative_to()` kept both, so `p.parent / p.name == p` was false for a path
  with a query. Is: every derivation that changes only the path keeps both, and
  a token in the query follows the children (`unk://h/d/f?sig=abc#frag`). The
  children of an `http:` or `dav:` listing are the exception: they are the
  `href`s of the reply resolved against the directory, so they carry neither,
  and `?sort=name`, which shapes an index, does not reach the files it lists
  (`directory / "f.txt"` keeps it). A `str` destination of `rename()`,
  `copy()` and `move()` is another resource and takes neither. What to do:
  nothing, unless a caller relied on the join dropping them; call
  `with_query(None)` and `with_fragment("")` on the result (or on the base)
  there.
- `URI.with_query(None)` removes the query. Was: a `TypeError` ("'NoneType' object
  is not iterable"). `with_fragment("")` removes the fragment as before.
- `file:` URIs keep an empty authority, and `==` reads a `str` operand as a
  URI. Was: `Uri("file:///etc/passwd")` was written `file:/etc/passwd` and
  `UriPath(LocalPath("C:/Windows/win.ini")).as_uri()` was
  `file:/C:/Windows/win.ini`, where `pathlib.Path.as_uri()` gives
  `file:///C:/Windows/win.ini`; `Uri("file:///etc/passwd") ==
  "file:///etc/passwd"` was false, and so were `Uri("HTTP://H/x") ==
  "HTTP://H/x"` and `Uri("http://h/a b") == "http://h/a b"`, because the text
  was compared as written. Is: an empty authority (`file:///x`,
  `Source.host == ""`) and none (`file:/x`, `Source.host is None`) are
  different URIs, each written as it was read; a path built from a local path
  object is written as `pathlib.Path.as_uri()` writes it (the characters
  `!$&'()*+,;=:@` stay literal in the path, where `pathlib` escapes them); and
  `==` parses a `str` operand before comparing it, so a URI equals any text
  that names it, and text that is not a URI is not equal to anything. What to
  do: compare URIs with `==` instead of comparing their text, and expect
  `file:///` where code tested `file:/`. A `Source` built by hand with host
  `""` now means an empty authority (`file://`): use `None` for none.
- The path of a `data:` URI is its payload, and `read_text()` uses the
  declared charset. Was: `name`, `parent`, `with_name()` and `/` cut the
  payload at a `/` (`data:text/plain;charset=utf-8,%C3%BCber` had the name
  `plain;charset=utf-8,über` and `d / "x"` was the other file
  `...%C3%BCber/x`), and `read_text()` decoded with the locale (`"Ã¼ber"` on
  Windows). Is: those derivations (`name`, `stem`, `suffix`, `suffixes`,
  `parent`, `parents`, `segments`, `with_name()`, `with_stem()`,
  `with_suffix()`, `with_segments()`, `/`, `joinpath()`, `relative_to()`,
  `is_relative_to()`, `match()` and a constructor given several parts) raise
  `NotImplementedError`, and `open()` in text mode and `read_text()` decode
  with the charset the URI declares (`DataURIPath.charset`, `"utf-8"` when it
  declares none). What to do: name a destination yourself when you copy a
  `data:` URI into a directory, pass `encoding=` to override the charset, and
  read the payload with `read_bytes()` instead of slicing the path.
- A write stream whose `with` block raised is not committed. Was: leaving a
  `with path.open("wb")` block through an exception closed the `http:` or
  `dav:` stream like a normal exit, so the partial buffer was sent with `PUT`
  and replaced the complete file (`write(b"tru")` then an error left
  `good.bin` holding `tru`). Is: any exception (a `KeyboardInterrupt` too)
  makes the block discard the stream, in binary and in text mode, and nothing
  is sent; the file keeps its content or is not created. `close()` outside a
  block and a block that ended normally send once, as before. The same holds
  for `ftp:` and `zip:`, whose streams are the `pathapi` ones. What to do:
  nothing, unless code relied on the partial upload; a local file still keeps
  what a failed block wrote, as `pathlib` does.
- A host keeps the spelling it was given. Was: the parser and the composer
  folded a host name to lower case, so `Source.parse("wss://root:pw@nasA:8443").host`
  was `nasa` and `str(Uri("wss://root:pw@nasA:8443/api"))` was
  `wss://root@nasa:8443/api`. Is: `Source.host` and the text keep `nasA`, and
  everything that compares hosts or keys on one folds the case itself: `==`,
  `hash()` and ordering of URIs, `same_authority()`, `is_relative_to()`,
  backend sharing, `rename()`, the same-file decisions of `copy()` and
  `move()`, the redirect origin that keeps `Authorization`, the proxy rules,
  `Source.is_local()` and the connection cache of `ftp:`. `http://NASA/x` and `http://nasa/x` are one
  server and equal URIs; their text differs. Two `Source` values compare as
  tuples, exactly; `compose_host()` and `compose_uri()` keep the case of a
  name; an internationalized name is still written in IDNA form. What to do:
  compare hosts with `uripath.source.same_authority()` or
  `uripath.source.fold_host()` instead of `source.host == "name"`, and key
  anything you keep per server on `fold_host(source.host)`.
- A constructor raises `TypeError` for a keyword argument it does not name.
  Was: `URI("x", anything=1)` and `URIPath("https://h/x", backnd=backend)`
  were accepted and the keyword ignored, so a misspelt `backend=` meant "use
  the default backend" (and the ambient credentials). Is: `TypeError:
  HTTPURIPath() got an unexpected keyword argument 'backnd'`. `URI` takes no
  keyword; a path takes `backend`, `schemesmap`, `findclass` and the ones its
  scheme class names in `_OPTIONS`; the path of a scheme that another
  distribution implements, when that distribution is not installed, takes any.
  What to do: correct or remove the stray keyword; a scheme class of your own
  that reads keywords lists them (`_OPTIONS = URIPath._OPTIONS | {"flavor"}`).
- Text that is not a URI raises `URISyntaxError` where it raised a bare
  `ValueError`: a port outside 0-65535, a malformed host or IPv6 address,
  `Source.parse()` of text with a path, a `zip:` URI without the scheme of
  its archive. It is a subclass of
  `ValueError`, so `except ValueError` still catches it. `URIPath.scheme_class()`
  of a scheme nobody registered raises `UnsupportedSchemeError`, also a
  `ValueError`. Both derive from `URIPathError`; a caller's bad argument stays a
  plain `ValueError` or `TypeError`. What to do: nothing; catch `URIPathError`
  to catch what the package raises on its own.
- Requests of `http:` and `dav:` send
  `User-Agent: uripath/<version>` instead of `User-Agent: pathlib-next`; the
  version is `uripath.__version__`. A backend's `headers=` still replaces it.
- A plugin registered in the `pathlib_next.schemes` entry-point group is not
  found. What to do: register it in `uripath.schemes`.
- The `requests` HTTP transport is provided by `pathapi-requests`.
  `HTTPURIPath.with_session()` and `PATHAPI_HTTP_TRANSPORT=requests` raise an `ImportError` naming that
  distribution without it, and a proxy URL the built-in transport cannot use
  (`socks5:`, `https:`) names it in its error too. What to do: install
  `pathapi-requests` where one of them is used; with it installed they
  send through its transport and nothing else is configured.
- `uritools` is not a dependency. The RFC 3986 split of a URI and its
  percent-encoding and -decoding are done on `urllib.parse`, with the results
  `uritools` gave for the same text: the same safe sets, invalid escapes left as
  they are, non-ASCII text kept, a lone surrogate or an escape that is not UTF-8
  carried through `surrogateescape`, an empty authority told from none.
  `import uripath` loads neither `uritools` nor `netimps`; `netimps` is
  imported where it is used. What to do: code that imports `uritools` itself
  installs it.
- The `uripath` command is rebuilt on `duho` and needs the `cli` extra:
  `pip install "uripath[cli]"`. Was: part of the base install. Without the
  extra the command (and `python -m uripath`) prints which extra to install on
  stderr and exits with status 1. The subcommands, their options and meanings,
  `-` for stdin and stdout, the exit statuses (0, 1 the operation failed, 2 a
  wrong invocation, 130 Ctrl-C, 141 the reader of stdout went away) and the
  `uripath: <Type>: <message>` line on stderr are as they were. What differs:
  - `uripath.cli.main(argv=None)` returns the status and reads and writes the
    process's standard streams. Was: `main(argv, *, stdin=, stdout=, stderr=)`
    with injectable streams, and `build_parser()` returning an `argparse`
    parser. Neither exists any more; build a command with `duho.parse` to test
    one.
  - Usage, `--help` and the wording of a usage error are `duho`'s, not
    `argparse`'s; a wrong invocation still exits with status 2.
  - Every command takes `-v`, `-q` and `--loglevel`, which set the level of the
    `uripath` logger. `sync -v`, which listed the changes made, is now a count
    (`-vv` is accepted) and lists them while `-v` is given more often than
    `-q`.
  - A boolean option that is on by default has both spellings:
    `--follow-symlinks` beside `--no-follow-symlinks`, `--preserve-metadata`
    beside `--no-preserve-metadata`, `--follow-mounts` beside
    `--no-follow-mounts`.
  - `--` ends the options and accepts no argument after it. Was: `argparse`
    took what followed as positional arguments, so `uripath rm -- -name`
    removed `-name`; write `uripath rm ./-name`.
- An `http:` or `dav:` write stream that is garbage collected without being closed sends
  nothing and emits a `ResourceWarning`; `pathlib-next` closed it, and so uploaded it.
  What to do: close the file, or use `with`.

[Unreleased]: https://github.com/jose-pr/uripath/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/jose-pr/uripath/releases/tag/v0.1.0
