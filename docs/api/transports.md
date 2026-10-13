# Transports

An HTTP transport sends one request and returns one response. `uripath` has a
built-in one (`HTTPTransport`, on `http.client`); another distribution provides
more by declaring an entry point in the `uripath.http_transports` group. The
functions below list them without importing any and load one by name.

::: uripath.transports
    options:
      show_if_no_docstring: true
      filters: ["!^_"]
