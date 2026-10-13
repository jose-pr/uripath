# `http:` and `dav:`

Both run on the standard library, through a transport that can be replaced
(`HTTPTransport` by default).

::: uripath.schemes.http
    options:
      members:
        - DEFAULT_TIMEOUT
        - MAX_LISTING_BYTES
        - HttpBackend
        - HTTPResponse
        - HTTPTransport
        - HttpPath
        - HttpWriteStream
        - HttpAppendStream
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.dav
    options:
      members:
        - DavPath
