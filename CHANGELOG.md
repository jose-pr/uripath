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

### Changed

- Import from `uripath` where the code imported from `pathlib_next.uri`:
  `from uripath import URI, URIPath`, `uripath.source`, `uripath.query` and
  `uripath.schemes.<scheme>`. `pathlib_next.uri` and `pathlib_next.tools.uripath`
  are not in this distribution.
- The classes spell their acronyms in capitals, and the class of a scheme is
  named `<Scheme>URIPath`, so `<Scheme>Path` stays the class that needs no URI.
  There is no alias for an old name: rename it where it is imported.

  | Was | Is |
  | --- | --- |
  | `Uri`, `UriPath`, `UriLike` | `URI`, `URIPath`, `URILike` |
  | `FileUri`, `DataUri` | `FileURIPath`, `DataURIPath` |
  | `ZipUri`, `TarUri`, `ArchiveUri` | `ZipURIPath`, `TarURIPath`, `ArchiveURIPath` |
  | `ArchiveZipUri`, `ArchiveTarUri` | `ArchiveZipURIPath`, `ArchiveTarURIPath` |
  | `FtpPath`, `HttpPath`, `DavPath` | `FTPURIPath`, `HTTPURIPath`, `DAVURIPath` |
  | `GitHubPath`, `GitLabPath`, `GitPath` | `GitHubURIPath`, `GitLabURIPath`, `GitURIPath` |
  | `GitHubGitPath`, `GitLabGitPath` | `GitHubGitURIPath`, `GitLabGitURIPath` |
  | `HttpBackend` | `HTTPBackend` |
  | `FtpBackend`, `BaseFtpBackend` | `FTPURIBackend`, `BaseFTPURIBackend` |
  | `HttpWriteStream`, `HttpAppendStream` | `HTTPWriteStream`, `HTTPAppendStream` |

  The `ftp:` backends are not `pathlib_next.ftp.FTPBackend` and `BaseFTPBackend`:
  those belong to one host, while `FTPURIBackend` connects to whichever server a
  path names.
- The entry-point group for third-party schemes is `uripath.schemes`. A plugin
  registered under `pathlib_next.schemes` is not found: register it under the
  new group.
- The `requests` HTTP transport is provided by `uripath-http-requests`.
  `HTTPURIPath.with_session()`, `RepoBackend(session=...)`, `RepoBackend(**requests_args)`
  and `PATHLIB_NEXT_HTTP_TRANSPORT=requests` raise an `ImportError` naming it;
  install it to use them. A proxy URL the built-in transport cannot use
  (`socks5:`, `https:`) names it in its error too.
- There are no extras. `uritools` and `netimps` are required dependencies, so
  `pip install uripath` is all that `pathlib-next[uri]` was; the `http`,
  `sftp`, `sftp-async`, `s3`, `gs` and `az` extras are the distributions named
  above.
