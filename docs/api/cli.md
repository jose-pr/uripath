# CLI API

The `uripath` console script and `python -m uripath`. Usage is described in the
[CLI guide](../guides/cli.md). `main` is the one name to call; the commands are
`duho` classes in the modules beside it (`uripath.cli.read`, `write`, `rm`,
`cp` and `sync`), and everything they do goes through the library.

::: uripath.cli
    options:
      show_if_no_docstring: true
      members: [main]
