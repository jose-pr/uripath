# `github:`, `gitlab:` and `git:`

None needs a client library: they send through the same transport as `http:`.

::: uripath.schemes._gitrepo
    options:
      members:
        - DEFAULT_TIMEOUT
        - BaseRepoBackend
        - InsecureTransportWarning
        - RepoBackend
      show_root_heading: true

::: uripath.schemes._gitrepo._RepoApiPath
    options:
      show_if_no_docstring: true
      filters: ["!^_"]

::: uripath.schemes.github.GitHubURIPath

::: uripath.schemes.gitlab.GitLabURIPath

::: uripath.schemes.git._base.GitURIPath

::: uripath.schemes.git.github.GitHubGitURIPath

::: uripath.schemes.git.gitlab.GitLabGitURIPath
