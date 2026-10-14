# `http:` and `dav:`

Both run on the standard library, through a transport that can be replaced.
The transport (`HTTPTransport` by default), `HTTPResponse` and the rules for
redirects and credentials are those of `pathapi.http`; see its
documentation.

::: uripath.schemes.HTTPURIPath
    options:
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.HTTPBackend

::: uripath.schemes.HTTPWriteStream

::: uripath.schemes.HTTPAppendStream

::: uripath.schemes.DAVURIPath

`pathapi.http.MAX_REPLY_BYTES` (8 MiB) bounds a reply the backend reads
whole, such as a directory index; assign a larger number to allow more.
