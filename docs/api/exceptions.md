# Exceptions

`URIPathError` is the base of what goes wrong at run time. A caller's bad
argument is a plain `ValueError` or `TypeError`, and a failed read or write is
the `OSError` of the kind `pathlib` raises.

::: uripath.exceptions
    options:
      show_if_no_docstring: true
      filters: ["!^_"]
