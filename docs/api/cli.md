# CLI API

The `uripath` console script and `python -m uripath`. Usage is described in the
[CLI guide](../guides/cli.md). Only `main` is public; the commands are classes
of the private modules beside it, and everything they do goes through the
library.

::: uripath.cli
    options:
      show_if_no_docstring: true
      members: [main]
