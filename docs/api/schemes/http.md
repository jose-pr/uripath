# `http:` and `dav:`

Both run on the standard library, through a transport that can be replaced
(`HTTPTransport` by default).

::: uripath.schemes.http
    options:
      members:
        - DEFAULT_TIMEOUT
        - MAX_LISTING_BYTES
        - HTTPBackend
        - HTTPResponse
        - HTTPTransport
        - HTTPURIPath
        - HTTPWriteStream
        - HTTPAppendStream
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.dav
    options:
      members:
        - DAVURIPath
