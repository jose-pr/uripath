# `http:` and `dav:`

Both run on the standard library, through a transport that can be replaced
(`HTTPTransport` by default).

::: uripath.schemes.HTTPURIPath
    options:
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.HTTPBackend

::: uripath.schemes.HTTPTransport

::: uripath.schemes.HTTPResponse

::: uripath.schemes.HTTPWriteStream

::: uripath.schemes.HTTPAppendStream

::: uripath.schemes.DAVURIPath

`uripath.schemes.MAX_LISTING_BYTES` (8 MiB) bounds a reply the backend reads
whole, such as a directory index; assign a larger number to allow more.
