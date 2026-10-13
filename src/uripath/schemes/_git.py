from __future__ import annotations

from .._uri import URI
from ..exceptions import URISyntaxError
from ._path import URIPath
from ._github import GitHubURIPath
from ._gitlab import GitLabURIPath


class GitURIPath(URIPath):
    """`git:` catch-all scheme for public Git hosts.

    `git://github.com/...` and `git://gitlab.com/...` auto-select the
    existing `github:`/`gitlab:` providers by host. Self-hosted or
    enterprise instances are intentionally ambiguous here and must use
    `git+github:`/`git+gitlab:` or the explicit `github:`/`gitlab:`
    schemes.
    """

    __SCHEMES = ("git",)
    __slots__ = ()

    @staticmethod
    def _normalize_host(host) -> str:
        # `str()`: an IP-literal host is an `ipaddress` object, not a str.
        return str(host or "").lower()

    @classmethod
    def _provider_cls(cls, source, path="", query="", fragment=""):
        """The provider class `git:` selects for `source`'s host; ValueError
        for a host it cannot auto-detect."""
        host = cls._normalize_host(source.host)
        if host in ("github.com", "www.github.com"):
            return GitHubURIPath
        if host in ("gitlab.com", "www.gitlab.com"):
            return GitLabURIPath
        # Redacted like the git-hosting schemes: the userinfo can be a
        # bare token, which `URI`'s own repr keeps.
        shown = GitHubURIPath._format_parsed_parts(
            source, path, query, fragment, sanitize=True
        )
        raise URISyntaxError(
            f"git: can only auto-detect github.com and gitlab.com; "
            f"use github:, gitlab:, git+github:, or git+gitlab: for {shown!r}"
        )

    def __new__(cls, *args, **kwargs):
        uri = URI(*args, **kwargs)
        provider_cls = cls._provider_cls(uri.source, uri.path, uri.query, uri.fragment)
        inst = URIPath.__new__(provider_cls, *args, **kwargs)
        inst._init(uri.source, uri.path, uri.query, uri.fragment, **kwargs)
        return inst


class GitHubGitURIPath(GitHubURIPath):
    """`git+github:` explicit GitHub-hosted repository scheme."""

    __SCHEMES = ("git+github",)
    __slots__ = ()


class GitLabGitURIPath(GitLabURIPath):
    """`git+gitlab:` explicit GitLab-hosted repository scheme."""

    __SCHEMES = ("git+gitlab",)
    __slots__ = ()
