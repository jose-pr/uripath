# Schemes

Every built-in implementation shares one contract: `exists()`, `is_dir()`,
`iterdir()`, `glob()`, `walk()`, `open()`/`read_text()`/`write_bytes()`,
`copy()`/`move()`, `rm()` and `PathSyncer` are derived from a few primitives
(`stat`, `_open`, listing, `_mkdir`, `unlink`, `rmdir`, `rename`, `chmod`).
Where a backend lacks a primitive, the operation raises
`NotImplementedError`; `move()` falls back to copy + delete when `rename()` is
unavailable or the target is elsewhere.

`UriPath("scheme://...")` returns the class registered for the scheme. None of
the schemes below needs a third-party client library. `sftp:`, `s3:`, `gs:`
and `az:` are provided by other distributions (see "Other distributions").

## Capability matrix

| Implementation | Read | Write | Append | List | mkdir | Delete | rename | chmod |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `file:` (`FileUri`) | Yes | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| `data:` (`DataUri`) | Yes | No | No | No | No | No | No | No |
| `zip:` (`ZipUri`) | Yes | Local `file:` archive | No | Yes | Local archive | Local archive | Local archive | No |
| `tar:` (`TarUri`) | Yes | No | No | Yes | No | No | No | No |
| `archive:` / `archive+zip:` / `archive+tar:` | As `zip:` or `tar:` for the detected or pinned format |  |  |  |  |  |  |  |
| `ftp:` / `ftps:` (`FtpPath`) | Yes | Yes | Yes (`APPE`) | Yes | Yes | Yes | Yes | `SITE CHMOD`, if the server has it |
| `http:` / `https:` (`HttpPath`) | Yes | Yes (`PUT`) | Yes (rewrite or `PATCH`) | Yes (HTML index) | No | Yes (`DELETE`) | No | No |
| `dav:` / `davs:` (`DavPath`) | Yes | Yes | No | Yes (`PROPFIND`) | Yes (`MKCOL`) | Yes | Yes (`MOVE`) | No |
| `github:` (`GitHubPath`) | Yes | No | No | Yes | No | No | No | No |
| `gitlab:` (`GitLabPath`) | Yes | No | No | Yes | No | No | No | No |
| `git:` / `git+github:` / `git+gitlab:` | As `github:`/`gitlab:` |  |  |  |  |  |  |  |

`stat()` works everywhere. `st_mtime` is real on every implementation except
`data:` and `github:`/`gitlab:`, where it is `0`. `symlink_to()` is
implemented by `file:` only; `readlink()` by `file:` and the archive schemes.

## Common behavior

- **Errors** map to pathlib's exception types (`FileNotFoundError`,
  `PermissionError`, `FileExistsError`, `IsADirectoryError`,
  `NotADirectoryError`, `OSError(ENOTEMPTY)`); network timeouts raise
  `TimeoutError`. Transport exceptions are not chained, because their text
  can carry credentials.
- **Credentials** in a URI are redacted from `str()`/`repr()` (the password;
  for `github:`/`gitlab:`/`git:` the whole userinfo). A backend (session,
  connection, token) is reused only for the same scheme, userinfo, host and
  port, so joining a path onto another host never sends it there.
- **`rename()`** stays on one endpoint: a target on another host
  or archive raises `NotImplementedError`, and `move()` copies and
  deletes instead. A `str` target is a path (not URI syntax); a relative one
  is a sibling.
- **Backends** are passed as `UriPath(uri, backend=...)` or
  `path.with_backend(backend)`, and inherited by every derived path. Without
  one, paths derived from one another (`root / name`, `parent`, ...) share the
  one backend the first of them builds, so 20 children of a fresh root use one
  connection; paths constructed separately do not share.

## Local files and data

- **`file:`** (`FileUri`) wraps a `LocalPath` (`filepath`) and delegates all
  I/O to it. `rename()` accepts local targets only.
- **`data:`** (`DataUri`, RFC 2397) keeps the whole content in the URI
  (`data:[<mediatype>][;base64],<data>`): a read-only single file with a
  `mediatype` property.

## HTTP and WebDAV

- **`http(s):`** (`HttpPath`) reads with `GET` (uncompressed) and `stat()`s
  with `HEAD`, falling back to `GET` on 405 and following a redirect once, at
  its `Location`; a final URL whose path ends in `/` is a directory. Listing
  parses Apache/nginx-style HTML indexes; a non-HTML
  response raises `NotADirectoryError`, and an HTML file cannot be told apart
  from an index page. An index is read like a file: one that is cut short or
  stalls raises (`OSError` or `TimeoutError`) instead of listing part of it,
  and one larger than `uripath.schemes.http.MAX_LISTING_BYTES` (8 MiB)
  raises `OSError` (`EFBIG`); assign a larger number to list it. Configure it with
  `path.with_transport(transport, headers=None, timeout=(10, 60),
  write_method="PUT", append_mode="rewrite")`; the default transport is the
  built-in one (see "Transports" below).
  - Writes send `write_method` with the whole body on close. `open("x")`
    calls `stat()` first: a file that exists raises `FileExistsError`, and so
    does any failure of that check other than not-found (nothing is sent).
    The upload carries `If-None-Match: *`, so a server that honours it
    answers 412 (`FileExistsError`) if the file appeared meanwhile.
  - `open("a")`: `append_mode="rewrite"` downloads, appends and re-uploads
    (works on any server, not atomic); `append_mode="patch"` sends `PATCH`
    with a `Content-Range` starting at the size the `HEAD` reply states
    (`OSError` if it has no `Content-Length`) and never falls back.
    A refused `PATCH` raises `PermissionError` (401, 403, 405, 501) or
    `OSError` with the HTTP status (other codes, such as 400). An `open("a")`
    that raises, because reading the current content or the `HEAD` failed,
    has uploaded nothing.
  - `unlink()` refuses a directory; `rmdir()` requires an empty one.
  - Requests time out after `(10, 60)` seconds (connect, read) unless a
    `timeout` is given; `timeout=None` waits forever.
  - The library follows redirects itself, up to 30, for `GET`, `HEAD` and
    `OPTIONS`, but not for `PROPFIND` or the writes: `PROPFIND`, `PUT`,
    `PATCH`, `DELETE`, `MKCOL`, `MOVE` and a custom `write_method` are never
    followed. A 307 or 308 (for `PROPFIND` also a 301, 302 or
    303) to the same scheme, host and port is sent once more with the same
    method, headers and body; any other 3xx, a redirect to another origin and
    a second redirect raise `OSError` (`EIO`) naming the status and the
    `Location`. Point the path at the final URL if the server redirects.
  - Credentials in the URL (`https://user:pw@host/`) are sent as an
    `Authorization: Basic` header, never inside the request URL; the octets of
    the percent-escapes are the credential (`caf%C3%A9` goes out as UTF-8
    bytes). The default transport never reads `~/.netrc`.
  - When a `GET` or `HEAD` is redirected to a different scheme, host or port,
    the library drops `Authorization` and nothing else: headers
    other than `Authorization` from `with_transport(headers=...)` (`X-Api-Key`,
    a vendor token header) go to the new host too. Keep a secret in
    `Authorization`, or point the path at the final URL.
  - A header or URL with a line break or other control character is a
    `ValueError`, raised before anything is sent.
  - The mode of `open()` is matched exactly: `"r+"`, `"w+"` and `"a+"` raise
    `NotImplementedError`.
- **`dav(s):`** (`DavPath`) is WebDAV (RFC 4918) over the equivalent
  `http(s):` URL, with the same `with_transport()`. `PROPFIND` gives real
  directory metadata, `MKCOL`/`PUT`/`DELETE`/`MOVE` full writes. A reply that
  is not a `multistatus` document, or that names neither the collection nor
  any member of it, raises `OSError` (`EIO`), and a listing keeps only the
  direct members of the collection it asked about. `unlink()`
  refuses a collection and `rmdir()` checks that it is empty (WebDAV
  `DELETE` is recursive); `rm(recursive=True)` is a single `DELETE`.
  `rename()` does not overwrite an existing target (`FileExistsError`).
  Uploads use `write_method` (default `PUT`) from `with_transport()`; append
  mode is not supported, so `append_mode` has no effect.

### Transports

`http:`, `dav:`, `github:`, `gitlab:` and `git:` send through a **transport**:
any object with `send(method, url, *, headers, body=None, timeout,
stream=False)` returning an `HTTPResponse`, and `close()`. The library, not the
transport, follows redirects, adds credentials and maps a status to an
exception, so every transport behaves alike.

- **`HTTPTransport`** (the default) is standard library only (`http.client`,
  `ssl`). `HTTPTransport(ssl_context=None, verify=True, proxies=None)`: `https:`
  is verified against the system trust store, or `ssl_context`;
  `verify=False` is the one switch that turns it off. It keeps one idle
  connection per thread and server, and sends a repeatable request again once
  when the server had closed that connection.
- **Proxies**: without `proxies=` the environment (`HTTP_PROXY`, `HTTPS_PROXY`,
  `ALL_PROXY`, `NO_PROXY`) decides. `proxies=` is an object indexed with the
  request URL that returns `None` (direct), a proxy, or an order of them to try
  when one cannot be reached; `KeyError` means direct. A proxy is a URL or an
  object with a `url`, so a proxy resolver of that shape works as it is. Only `http://`
  proxies are supported (`CONNECT` for `https:`); for SOCKS or an `https://`
  proxy use the `requests` transport of `uripath-http-requests`.
- **The `requests` transport** is provided by the `uripath-http-requests`
  distribution (`~/.netrc`, `REQUESTS_CA_BUNDLE` and certifi, SOCKS proxies,
  digest and NTLM authentication, cookies, mounted adapters). Without it,
  `path.with_session(...)` and `PATHLIB_NEXT_HTTP_TRANSPORT=requests` raise an
  `ImportError` that names it.

## FTP

**`ftp(s):`** (`FtpPath`) uses stdlib `ftplib`, through
[`pathlib_next.ftp.FTPPath`](https://jose-pr.github.io/pathlib-next/api/ftp/), which needs no URI: `FTPPath("/pub/x",
host="h", user="u", tls=True)` is the same tree without a `ftp://` string.

- `FtpBackend(timeout=30.0, ssl_context=None, verify=True)` configures it.
  Sockets time out after 30 seconds by default (`timeout=None` waits forever).
- **`ftps:` verifies the server certificate and host name** before logging in
  and reuses the TLS session on data connections. For a private CA pass
  `FtpBackend(ssl_context=ssl.create_default_context(cafile=...))`;
  `FtpBackend(verify=False)` turns verification off.
- Paths built without `backend=` share one default backend, with one cached
  connection per server and thread, closed when the thread ends. A connection
  idle for more than `IDLE_PROBE_SECONDS` (1 second) is probed with `NOOP`
  before use and replaced if the server dropped it.
- A listing uses `MLSD` (type, size and UTC modification time in one round
  trip) and `stat()` uses `MLST` where the server offers it; without them the
  listing falls back to `NLST` and the stat to `SIZE`/`CWD`.
- Reads download the whole file into memory; writes are buffered in memory
  and uploaded on close. `chmod()` uses `SITE CHMOD` and raises
  `NotImplementedError` when the server lacks it.

## Other distributions

These schemes and this transport are known to `uripath` and provided by other
distributions. A path of one of the schemes builds, joins, compares and prints
without it; the first operation that needs the server (`stat()`, `exists()`,
`open()`, `iterdir()`, ...) raises an `ImportError` that names what to install.

| Provides | Install |
| --- | --- |
| `sftp:` | `pip install "uripath-sftp[paramiko]"` (or `[asyncssh]`) |
| `s3:` | `pip install "uripath-objstore[s3]"` |
| `gs:` | `pip install "uripath-objstore[gs]"` |
| `az:` | `pip install "uripath-objstore[az]"` |
| the `requests` HTTP transport | `pip install uripath-http-requests` |

## Archives

**`zip:`/`tar:`** address an entry inside an archive:
`zip:<archive-uri>!/<inner-path>` (the Java-style `!/` separator of JAR URLs).
The `<archive-uri>` is any absolute URI with an explicit scheme, so
`zip:file:///backups/site.zip!/index.html` and
`zip:ftp://host/nightly.zip!/index.html` work the same way. `name`,
`parent`, `glob()`, ... operate on the inner path.

The members are read and written by [`pathlib_next.archive`](https://jose-pr.github.io/pathlib-next/api/archive/)
(`ZipPath`, `TarPath`, `ArchivePath`), which take the archive as any `Path` and
need no URI: `ZipPath("index.html", archive="/backups/site.zip")`.

- **Writing** (new members, overwriting, `mkdir()`, `unlink()`, `rmdir()`,
  `rename()`) works for zip archives whose outer URI is a local `file:` path.
  Each change replaces the archive atomically (temporary file, then
  `os.replace`) and keeps the other members' metadata, the archive comment and
  any leading bytes. Every other outer scheme is read-only and is read into
  memory.
- **`with path.batch():`** holds every change made to a zip while the
  block is open and replaces the archive once when it ends, instead of
  once per change. Inside the block every path of the archive reads the
  held changes and the file is not touched; an exception leaves the
  archive byte for byte as it was. `copy(recursive=True)` into a zip and
  `PathSyncer` onto one open it themselves: copying 300 files is one
  rewrite, not 300, and a copy that fails part way leaves the archive
  unchanged. Another thread using the archive waits for the block.
- **Links.** A tar symlink and a zip entry whose Unix mode says link are
  symbolic links: `is_symlink()`, `readlink()` and `lstat()` work, and
  `stat()`, `open()` and `iterdir()` follow them inside the archive. A
  link that is absolute, climbs out of the archive or points at nothing
  is `FileNotFoundError`, a loop `OSError(ELOOP)`; at most 40 links are
  followed. `walk()` and `glob()` list a link and do not enter it unless
  asked to, `rm()` removes the link and never its target, and
  `copy(follow_symlinks=False)` recreates it. A listing that does follow
  links (`walk(follow_symlinks=True)`, `copy()`'s default, `PathSyncer`)
  follows one directory link per path and never a link to its own
  directory or an ancestor, which is an error for that entry: spell the
  path to go further. Nothing is written through a link, and none can be
  created.
- **`tar:`** (also `.tar.gz`/`.tar.bz2`/`.tar.xz`) is read-only.
- **`archive:`** detects the format from the outer name, then from the file's
  magic bytes, on first use (building or printing a path reads nothing);
  `archive+zip:`/`archive+tar:` pin it. All spellings of one archive share one
  open handle. A remote outer is read once and kept while a path to it lives;
  `path.refresh()` makes the next use read it again.
- **Cost.** Listing and `stat()` are served from a table built once per open
  archive. A member is read into memory up to 16 MiB and into a temporary file
  beyond that. A zip change copies the members it does not touch without
  decompressing them. A new zip member is stored deflated.
- An archive inside an archive is addressed by nesting
  (`zip:zip:file:///outer.zip!/inner.zip!/x.txt`) and is read-only; a `!/`
  inside a member name is written `%21/`.
- Member names are normalized as POSIX relative paths, the same way for
  every format: `./x`, `a//b`, `a/./b` and `a/b/../c` all resolve, so a
  member lists and reads under one name however the archive was written
  (`tar -C dir .` and `shutil.make_archive` prefix every member with `./`).
  The spelling as written still works.
- Members whose names would escape the archive (`..` past the root, or an
  absolute path) have no name inside it: never listed, never readable. A
  name that merely a Windows destination would misread -- `C:drive.txt`, or
  one containing `\` -- is a normal member, since both are ordinary
  filenames on POSIX; copying or extracting it onto a Windows path is what
  refuses it. Exception types are the POSIX ones on every platform.

## Git hosting

**`github:`/`gitlab:`** (`<scheme>://host/owner/repo/path/in/repo?ref=<ref>`)
are read-only views of a repository over the REST APIs, sent through the
HTTP transport.

- `ref` (branch, tag or SHA) is optional and carried to every child path.
  Without it, `github:` uses the default branch server-side; `gitlab:` looks
  the default branch up once per backend.
- `host` defaults to `github.com`/`gitlab.com`. Another host is GitHub
  Enterprise (`https://{host}/api/v3`) or self-hosted GitLab
  (`https://{host}/api/v4`); `RepoBackend(api_base=...)` overrides the API
  root. A GitLab project in a subgroup uses GitLab's separator:
  `gitlab://host/group/subgroup/project/-/path`.
- Authentication: `RepoBackend(token=...)`, or the token in the URI userinfo,
  as the password (`github://x-access-token:TOKEN@github.com/owner/repo`) or
  bare (`github://TOKEN@github.com/...`). These schemes redact the whole
  userinfo from `str()`, `repr()`, `as_posix()` and error messages. A token
  sent over plain `http://` to a host other than loopback (an `api_base` you
  set) is still sent, with an `InsecureTransportWarning`.
- Owner, repository and every path segment are percent-encoded into the API
  URL, and a `.` or `..` segment (made with `with_name("..")`, say) raises
  `ValueError` rather than leaving the repository's API root.
- Requests time out after `(10, 60)` seconds (`RepoBackend(timeout=...)`).
  Rate-limit replies raise `OSError(EAGAIN)`.
- GitHub listings come from the contents API (with its type and size) and
  switch to the Git Trees API for directories at its 1,000-entry cap; file
  bodies use the raw media type. GitLab's tree listing has no sizes, so file
  entries are `stat()`ed on demand (a `HEAD` request, no file content).
  Symlinks and submodules read as plain files. Git has no empty directories.
- A reply that is not the shape the API documents (a proxy's HTML page,
  `null`, a truncated body, an array where an object belongs) raises
  `OSError` (`EIO`) naming the path; `exists()` is `False`.
- **`git:`** detects the provider for `github.com` and `gitlab.com` only;
  other hosts raise `ValueError` and need `github:`/`gitlab:` or the pinned
  `git+github:`/`git+gitlab:` forms.

See [Divergences from pathlib](../divergences.md) for the reasons behind these
choices. Every class and backend signature is in the API reference:
[`file:`/`data:`](../api/schemes/local.md),
[`http:`/`dav:`](../api/schemes/http.md), [`ftp:`](../api/schemes/ftp.md),
[archives](../api/schemes/archive.md) and
[`github:`/`gitlab:`/`git:`](../api/schemes/git.md).
