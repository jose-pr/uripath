from __future__ import annotations

from ..gitlab import GitLabURIPath


class GitLabGitURIPath(GitLabURIPath):
    """`git+gitlab:` explicit GitLab-hosted repository scheme."""

    __SCHEMES = ("git+gitlab",)
    __slots__ = ()
