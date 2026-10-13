# `github:`, `gitlab:` and `git:`

None needs a client library: they send through the same transport as `http:`.

::: uripath.schemes.RepoBackend

::: uripath.schemes.BaseRepoBackend

`GitHubURIPath` and `GitLabURIPath` share a base class; its properties
(`owner`, `repo`, `repo_path`, `ref`) and methods are listed here once.

::: uripath.schemes._gitrepo._RepoAPIPath
    options:
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.GitHubURIPath

::: uripath.schemes.GitLabURIPath

::: uripath.schemes.GitURIPath

::: uripath.schemes.GitHubGitURIPath

::: uripath.schemes.GitLabGitURIPath
