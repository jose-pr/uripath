from __future__ import annotations

from ..github import GitHubURIPath


class GitHubGitURIPath(GitHubURIPath):
    """`git+github:` explicit GitHub-hosted repository scheme."""

    __SCHEMES = ("git+github",)
    __slots__ = ()
