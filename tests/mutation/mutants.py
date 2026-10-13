"""The mutation list: one single-line change to a guard of the library per
entry, and the tests that must fail because of it.

`run.py` applies each entry to a temporary copy of `src/uripath`. `old`
is the exact text of the line (or lines) to replace and must occur once in
`file`, which is relative to `src/uripath`; when the code moves on and
the text goes, the entry is reported stale until it is re-expressed. `tests`
are pytest arguments (node ids, or a file when any of its tests may be the
one to catch the mutant) that all pass on the unmutated code. README.md says
how to add an entry.
"""

from __future__ import annotations

from typing import NamedTuple


class Mutant(NamedTuple):
    id: str
    file: str
    old: str
    new: str
    tests: tuple[str, ...]
    note: str
    platform: str | None = None


MUTANTS: list[Mutant] = []


def mutant(
    id: str,
    file: str,
    old: str,
    new: str,
    tests,
    note: str,
    platform: str | None = None,
) -> None:
    """Add an entry to the list. `tests` is one pytest argument or a sequence;
    `platform` is the `os.name` its tests need ("nt"), or None for any."""
    if isinstance(tests, str):
        tests = (tests,)
    MUTANTS.append(Mutant(id, file, old, new, tuple(tests), note, platform))


# --- http: and dav: deletes ---------------------------------------------------

mutant(
    "http-unlink-of-a-directory",
    "schemes/_http/_path.py",
    "        if self.is_dir():\n            raise IsADirectoryError(\n",
    "        if False:\n            raise IsADirectoryError(\n",
    "tests/test_http.py::test_http_unlink_on_directory_sends_no_delete",
    "HTTPURIPath.unlink() sends DELETE for a collection",
)
mutant(
    "http-rmdir-of-a-file",
    "schemes/_http/_path.py",
    "        if not self.is_dir():\n            raise NotADirectoryError(self)\n",
    "        if False:\n            raise NotADirectoryError(self)\n",
    "tests/test_http.py::test_http_rmdir_on_file_raises_notadirectoryerror",
    "HTTPURIPath.rmdir() sends DELETE for a file",
)
mutant(
    "http-rmdir-of-a-non-empty-directory",
    "schemes/_http/_path.py",
    '        for _ in self._scandir():\n            raise OSError(_errno.ENOTEMPTY, "Directory not empty", str(self))\n        self._delete()\n',
    "        self._delete()\n",
    "tests/test_http.py::test_http_rmdir_not_empty",
    "HTTPURIPath.rmdir() sends DELETE for a directory that lists children",
)
mutant(
    "http-delete-answered-404-with-missing-ok",
    "schemes/_http/_path.py",
    "                if missing_ok:\n                    return\n                raise FileNotFoundError(self)\n",
    "                if False:\n                    return\n                raise FileNotFoundError(self)\n",
    "tests/test_http.py::test_http_unlink_missing_ok_accepts_a_delete_answered_404",
    "unlink(missing_ok=True) raises for a DELETE answered 404",
)
mutant(
    "dav-delete-answered-404-without-missing-ok",
    "schemes/_dav.py",
    "        except FileNotFoundError:\n            if not missing_ok:\n                raise\n",
    "        except FileNotFoundError:\n            if False:\n                raise\n",
    "tests/test_webdav.py::test_unlink_without_missing_ok_raises_for_a_delete_answered_404",
    "unlink() swallows a DELETE answered 404 although missing_ok is False",
)

# --- guards of the library, from the first review of the suite -------------
mutant(
    "source-repr-shows-the-password",
    "source/_source.py",
    'f"userinfo={self._redacted_userinfo()!r}, host={self.host!r}, "',
    'f"userinfo={self.userinfo!r}, host={self.host!r}, "',
    "tests/test_uri_parse.py::test_source_str_and_repr_redact_password",
    "Source.__repr__ shows the password",
)
mutant(
    "source-str-shows-the-password",
    "source/_source.py",
    "        return self.as_str(sanitize=True)\n",
    "        return self.as_str(sanitize=False)\n",
    "tests/test_uri_parse.py::test_source_str_and_repr_redact_password",
    "Source.__str__ shows the password",
)
mutant(
    "http-listing-keeps-unsafe-names",
    "schemes/_http/_path.py",
    "            if not _providers.is_safe_child_name(name):\n",
    "            if False:\n",
    "tests/test_http.py::test_http_listing_leaves_out_a_name_that_is_not_a_safe_component",
    "HTTPURIPath listing filter no-op",
)
mutant(
    "dav-listing-keeps-unsafe-names",
    "schemes/_dav.py",
    "            if _providers.is_safe_child_name(name):\n",
    "            if True:\n",
    "tests/test_webdav.py::test_propfind_dot_entries_are_not_children",
    "DAVURIPath listing filter no-op",
)
mutant(
    "uri-same-filesystem-always-true",
    "schemes/_path.py",
    "        return mine is None or theirs is None or mine is theirs\n",
    "        return True\n",
    "tests/test_same_filesystem_uri.py::test_two_supplied_backends_are_two_hosts",
    "URIPath._same_filesystem always True",
)
mutant(
    "uri-same-filesystem-always-false",
    "schemes/_path.py",
    "        return mine is None or theirs is None or mine is theirs\n",
    "        return False\n",
    "tests/test_same_filesystem_uri.py::test_separately_built_paths_to_one_url_are_the_same_file",
    "URIPath._same_filesystem always False (self-copy guard off for remote)",
)
mutant(
    "http-404-is-a-generic-oserror",
    "schemes/_http/_errors.py",
    "        if status in (404, 410):\n            raise _path_error(FileNotFoundError, path_obj) from None\n",
    "        if status in (410,):\n            raise _path_error(FileNotFoundError, path_obj) from None\n",
    "tests/test_destructive_safety.py::test_copy_http_404_source_leaves_local_target_intact",
    "HTTP 404 maps to generic OSError(EIO)",
)
mutant(
    "http-connection-error-chains-the-request-error",
    "schemes/_http/_errors.py",
    '        raise ConnectionError(\n            f"Connection error for {path_obj} ({type(e).__name__})"\n        ) from None\n',
    '        raise ConnectionError(\n            f"Connection error for {path_obj} ({type(e).__name__})"\n        ) from e\n',
    "tests/test_transport_security.py::test_http_refused_connection_carries_no_password",
    "HTTP ConnectionError chains the requests exception (may carry proxy creds)",
)
mutant(
    "rename-accepts-another-location",
    "_uri.py",
    "        if not self._same_location(result):\n",
    "        if False:\n",
    "tests/test_routing.py::test_ftp_rename_to_another_server_raises_not_implemented",
    "rename() no longer refuses a target on another host/bucket",
)
mutant(
    "uri-str-shows-the-password",
    "_uri.py",
    "        return self.as_uri(sanitize=True)\n",
    "        return self.as_uri(sanitize=False)\n",
    "tests/test_transport_security.py::test_http_error_text_and_traceback_carry_no_password",
    "str(URI) shows the password",
)
mutant(
    "http-request-url-keeps-the-password",
    "schemes/_http/_follow.py",
    "    return url[:start] + hostport + url[end:], (auth if any(auth) else None)\n",
    "    return url, (auth if any(auth) else None)\n",
    "tests/test_transport_security.py::test_http_sends_userinfo_as_authorization_not_in_url",
    "HTTP requests keep user:password in the request URL",
)
mutant(
    "http-403-is-a-generic-oserror",
    "schemes/_http/_errors.py",
    "        elif status in (401, 403):\n",
    "        elif status in (401,):\n",
    "tests/test_transport_security.py::test_http_error_text_and_traceback_carry_no_password",
    "HTTP 403 maps to generic OSError(EIO)",
)
mutant(
    "http-timeout-chains-the-request-error",
    "schemes/_http/_errors.py",
    '        raise TimeoutError(f"Timeout for {path_obj} ({type(e).__name__})") from None\n',
    '        raise TimeoutError(f"Timeout for {path_obj} ({type(e).__name__})") from e\n',
    "tests/test_transport_security.py::test_http_timeout_carries_no_password",
    "HTTP TimeoutError chains the requests exception",
)
mutant(
    "uri-backend-inherited-by-another-endpoint",
    "schemes/_path.py",
    "            if source is mine or _same_authority(source, mine):\n                return backend, self._backend_derived\n",
    "            if True:\n                return backend, self._backend_derived\n",
    "tests/test_uri_path.py::test_a_same_endpoint_uri_destination_keeps_the_configured_backend",
    "a copy() destination on another host reuses this path's backend and its credentials",
)
mutant(
    "uri-join-keeps-a-backend-of-another-endpoint",
    "schemes/_path.py",
    "            if not _same_authority(segment.source, source):\n                continue\n            if backend is not None:",
    "            if False:\n                continue\n            if backend is not None:",
    "tests/test_backend_family.py::test_a_path_that_crosses_to_another_endpoint_builds_its_own",
    "a backend held by a join segment crosses to a path on another endpoint",
)
mutant(
    "http-write-redirect-reads-as-success",
    "schemes/_http/_follow.py",
    "    if not 300 <= resp.status < 400:\n        return resp\n    location = redirect_location(url, resp)",
    "    if True:\n        return resp\n    location = redirect_location(url, resp)",
    "tests/test_http_writes.py",
    "a write answered by a redirect that is not followed reads as done",
)
mutant(
    "http-write-follows-redirects-to-another-host",
    "schemes/_http/_follow.py",
    '    elif origin(location) != origin(url):\n        reason = "it leaves the scheme, host and port of the request"\n',
    '    elif False:\n        reason = "it leaves the scheme, host and port of the request"\n',
    "tests/test_http_writes.py",
    "a write is sent again to the host a 307 names, with its body and credentials",
)
mutant(
    "http-write-stream-uploads-before-it-is-ready",
    "schemes/_http/_streams.py",
    "            if self._ready:\n                self._upload(self.getvalue())\n",
    "            if True:\n                self._upload(self.getvalue())\n",
    "tests/test_http_writes.py",
    "a write stream whose constructor raised uploads its half-built buffer when collected",
)
# --- github: a HEAD reply that is not the API's own -----------------------------

mutant(
    "github-head-believes-a-reply-that-is-not-the-api-s",
    "schemes/_github.py",
    '            if "X-GitHub-Media-Type" not in resp.headers:\n                return None\n            _raise_for_status(resp)',
    "            _raise_for_status(resp)",
    "tests/test_github_stat.py::test_a_reply_that_is_not_the_api_s_own_is_not_believed",
    "a proxy's reply to a HEAD is read as the size of the file, or as its absence",
)
# --- the scheme registry: a name is held by one class -----------------------------

_SCHEME_TESTS = "tests/test_scheme_registry.py"

mutant(
    "scheme-registry-second-claim-is-dropped-silently",
    "schemes/_registry.py",
    "            elif name in _REPLACED and _is_builtin_class(name, cls):\n",
    "            elif True:\n",
    (
        f"{_SCHEME_TESTS}::test_a_second_class_listing_a_scheme_raises_at_definition",
        f"{_SCHEME_TESTS}::test_a_class_refused_for_one_name_registers_none_of_its_names",
    ),
    "a second class listing a held scheme is neither refused nor registered",
)
mutant(
    "scheme-registry-built-in-name-is-free-until-its-module-is-imported",
    "schemes/_registry.py",
    "                if name in _BUILTIN_SCHEMES and not _is_builtin_class(name, cls):\n",
    "                if False:\n",
    f"{_SCHEME_TESTS}::test_a_built_in_scheme_is_refused_before_its_module_is_imported",
    "a class takes a built-in scheme whose module has not been imported yet",
)
mutant(
    "scheme-registry-built-in-class-refused-after-a-replacement",
    "schemes/_registry.py",
    "            elif name in _REPLACED and _is_builtin_class(name, cls):\n",
    "            elif False:\n",
    f"{_SCHEME_TESTS}::test_a_replaced_built_in_scheme_stays_replaced_when_its_module_is_imported",
    "importing a built-in module fails once a class has replaced one of its schemes",
)
mutant(
    "scheme-lookup-asks-entry-points-before-the-built-in-table",
    "schemes/_path.py",
    "            cls._load_builtin_scheme(scheme, strict=strict)\n"
    "            or cls._load_entry_point(scheme)\n",
    "            cls._load_entry_point(scheme)\n"
    "            or cls._load_builtin_scheme(scheme, strict=strict)\n",
    f"{_SCHEME_TESTS}::test_an_entry_point_named_like_a_built_in_scheme_does_not_displace_it",
    "a distribution's entry point for a built-in name is loaded ahead of the built-in",
)
mutant(
    "scheme-listing-leaves-out-schemes-not-imported-yet",
    "schemes/_path.py",
    "                    *_BUILTIN_SCHEMES,\n                    *_elsewhere.SCHEMES,\n                    *_declared_entry_points(),\n",
    "",
    (
        f"{_SCHEME_TESTS}::test_schemes_lists_every_built_in_name_without_importing_its_module",
        f"{_SCHEME_TESTS}::test_schemes_lists_an_entry_point_whose_module_is_not_imported",
    ),
    "schemes() lists only the classes already imported",
)
mutant(
    "scheme-listing-leaves-out-the-schemes-provided-elsewhere",
    "schemes/_path.py",
    "                    *_elsewhere.SCHEMES,\n",
    "",
    "tests/test_elsewhere.py::test_a_scheme_provided_elsewhere_is_listed",
    "schemes() does not list sftp, s3, gs and az",
)
mutant(
    "scheme-class-of-a-scheme-provided-elsewhere-does-not-raise",
    "schemes/_path.py",
    "            if strict:\n                raise _elsewhere.not_installed(scheme)\n",
    "            if False:\n                raise _elsewhere.not_installed(scheme)\n",
    "tests/test_elsewhere.py::test_the_scheme_class_of_a_scheme_provided_elsewhere_names_what_to_install",
    "scheme_class('sftp') returns the stand-in instead of raising ImportError",
)
mutant(
    "with-session-builds-a-backend-without-the-requests-distribution",
    "schemes/_http/_path.py",
    "        raise _elsewhere.requests_transport_missing()\n",
    "        return self\n",
    "tests/test_elsewhere.py::test_with_session_names_the_distribution_that_provides_the_transport",
    "with_session() answers as if a requests transport were installed",
)
mutant(
    "scheme-registry-same-qualified-name-in-another-module-is-the-same-class",
    "schemes/_registry.py",
    "    return a.__module__ == b.__module__ and a.__qualname__ == b.__qualname__\n",
    "    return a.__qualname__ == b.__qualname__\n",
    f"{_SCHEME_TESTS}::test_a_class_of_the_same_qualified_name_in_another_module_is_still_refused",
    "a class of another module takes a scheme from a class that has the same name",
)

# --- http transports: the guards every transport keeps --------------------------

_HTTP_PKG = "schemes/_http"

mutant(
    "http-authorization-kept-across-origins",
    f"{_HTTP_PKG}/_follow.py",
    '        if origin(current) != home:\n            headers = drop_header(headers, "Authorization")\n',
    '        if False:\n            headers = drop_header(headers, "Authorization")\n',
    (
        "tests/test_http_redirects.py::test_authorization_is_dropped_by_a_redirect_to_another_port",
        "tests/test_http_redirects.py::test_authorization_follows_only_a_redirect_that_keeps_scheme_host_and_port",
    ),
    "a followed redirect to another scheme, host or port carries Authorization along",
)
mutant(
    "http-redirect-limit-off-by-one",
    f"{_HTTP_PKG}/_follow.py",
    "        if hops >= MAX_REDIRECTS:",
    "        if hops > MAX_REDIRECTS:",
    "tests/test_http_redirects.py::test_a_redirect_loop_stops_after_thirty_redirects",
    "a GET follows one redirect more than the limit",
)
mutant(
    "http-unrepeatable-request-resent",
    f"{_HTTP_PKG}/_builtin.py",
    "                if reused and repeatable:\n                    connection, reused = None, False\n                    continue\n                raise dropped.error from None",
    "                if reused:\n                    connection, reused = None, False\n                    continue\n                raise dropped.error from None",
    (
        "tests/test_http_pool.py::test_a_request_that_cannot_be_repeated_is_not_sent_again",
        "tests/test_http_pool.py::test_a_body_that_cannot_be_sent_twice_is_not_sent_again",
    ),
    "a POST, or a PUT with a file body, is sent again on a new connection when the server dropped the old one",
)
mutant(
    "http-timeout-treated-as-a-dropped-connection",
    f"{_HTTP_PKG}/_builtin.py",
    "            BrokenPipeError,\n            _ssl.SSLEOFError,",
    "            OSError,\n            _ssl.SSLEOFError,",
    "tests/test_http_pool.py::test_a_timeout_on_a_reused_connection_is_not_sent_again",
    "a request that timed out on a reused connection is sent again",
)
mutant(
    "http-stale-connection-trusted-by-an-unrepeatable-request",
    f"{_HTTP_PKG}/_builtin.py",
    "            and _now() - connection.released_at > REUSE_WINDOW",
    "            and _now() - connection.released_at > REUSE_WINDOW + 1e9",
    "tests/test_http_pool.py::test_a_request_that_cannot_be_repeated_does_not_trust_a_stale_connection",
    "a POST uses an idle connection however long ago it last carried a reply",
)
mutant(
    "http-verification-off-by-default",
    f"{_HTTP_PKG}/_builtin.py",
    '        verify: bool = True,\n        proxies: "_ty.Any" = None,',
    '        verify: bool = False,\n        proxies: "_ty.Any" = None,',
    "tests/test_http_tls.py::test_a_server_of_an_unknown_authority_is_refused_by_default",
    "the built-in transport accepts any certificate unless told to verify",
)
mutant(
    "http-verify-false-beats-the-ssl-context",
    f"{_HTTP_PKG}/_builtin.py",
    "        if self._ssl_context is not None:\n            return self._ssl_context",
    "        if self._ssl_context is not None and self._verify:\n            return self._ssl_context",
    "tests/test_http_tls.py::test_an_ssl_context_wins_over_verify_false",
    "verify=False replaces an ssl_context the caller gave",
)
mutant(
    "http-proxy-credentials-in-a-repr",
    f"{_HTTP_PKG}/_proxies.py",
    '        return f"ProxyAddress({self.host!r}, {self.port})"',
    '        return f"ProxyAddress({self.host!r}, {self.port}, {self.authorization!r})"',
    "tests/test_http_proxy.py::test_proxy_credentials_are_in_no_repr",
    "a proxy's Proxy-Authorization value shows in its repr",
)
mutant(
    "http-proxy-credentials-in-a-message",
    f"{_HTTP_PKG}/_proxies.py",
    '            f"the built-in HTTP transport has no {scheme!r} proxy support; "\n            + REQUESTS_HINT,',
    '            f"the built-in HTTP transport has no {scheme!r} proxy support ({url}); "\n            + REQUESTS_HINT,',
    "tests/test_http_proxy.py::test_a_proxy_scheme_that_is_not_http_is_refused_naming_the_other_transport",
    "the error for an unsupported proxy scheme quotes the proxy URL with its credentials",
)
mutant(
    "http-header-line-break-accepted",
    f"{_HTTP_PKG}/_headers.py",
    r'_CONTROL = _re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")',
    r'_CONTROL = _re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")',
    "tests/test_http_transport.py::test_a_header_with_a_line_break_or_a_bad_name_is_refused_before_sending",
    "a header value with a bare line feed is sent",
)
mutant(
    "http-url-line-break-accepted",
    f"{_HTTP_PKG}/_headers.py",
    r'_URL_CONTROL = _re.compile(r"[\x00-\x1f\x7f]")',
    r'_URL_CONTROL = _re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")',
    "tests/test_http_transport.py::test_a_url_with_a_control_character_is_refused_before_sending",
    "a URL with a line break or a tab reaches the request line",
)
mutant(
    "http-short-body-read-as-complete",
    f"{_HTTP_PKG}/_builtin.py",
    "        if self._expected is not None and self._received < self._expected:",
    "        if False:",
    "tests/test_http_transport.py::test_a_body_shorter_than_its_length_is_an_io_error_not_a_short_read",
    "a body that ends before its Content-Length reads as a complete one",
)
mutant(
    "http-inflation-not-bounded",
    f"{_HTTP_PKG}/_response.py",
    "_STEP = 256 * 1024",
    "_STEP = 1 << 40",
    "tests/test_http_transport.py::test_a_small_body_that_inflates_enormously_is_read_in_bounded_steps",
    "a gzip body is inflated whole into memory because a header says it is small",
)
mutant(
    "http-closed-stream-still-read",
    f"{_HTTP_PKG}/_response.py",
    "        if self._closed and not self._kept:",
    "        if False:",
    "tests/test_http_transport.py::test_reading_a_streamed_reply_after_closing_it_is_an_error",
    "a closed streaming reply keeps handing out bytes",
)
mutant(
    "http-idle-connection-limit",
    f"{_HTTP_PKG}/_pool.py",
    "MAX_IDLE_PER_THREAD = 8",
    "MAX_IDLE_PER_THREAD = 100",
    "tests/test_http_pool.py::test_a_thread_keeps_at_most_eight_idle_connections",
    "a thread keeps more than eight idle connections",
)
mutant(
    "http-default-transport-is-requests",
    f"{_HTTP_PKG}/_select.py",
    'DEFAULT_TRANSPORT = "builtin"',
    'DEFAULT_TRANSPORT = "requests"',
    "tests/test_http_default.py::test_without_a_setting_the_built_in_transport_is_used",
    "a backend without a transport builds a requests session",
)
mutant(
    "http-idle-connection-used-without-a-check",
    f"{_HTTP_PKG}/_builtin.py",
    "        if connection is not None and _unusable(connection.http.sock):\n",
    "        if False:\n",
    (
        "tests/test_http_pool.py::test_bytes_the_server_sends_after_a_reply_are_not_the_next_reply",
        "tests/test_http_pool.py::test_an_idle_connection_the_server_closed_is_replaced_before_sending",
    ),
    "an idle connection the server closed, or sent extra bytes on, carries the next request",
)
mutant(
    "http-closed-connection-reopens-itself",
    f"{_HTTP_PKG}/_builtin.py",
    "        http.auto_open = 0\n",
    "        http.auto_open = 1\n",
    (
        "tests/test_http_pool.py::test_a_connection_closed_before_the_request_is_written_is_not_reopened",
        "tests/test_http_pool.py::test_a_transport_closed_before_the_request_is_written_does_not_send_it",
        "tests/test_http_pool.py::test_a_body_that_is_being_sent_when_the_transport_is_closed_is_not_finished_in_the_clear",
    ),
    "http.client reconnects a closed connection by itself, in plain TCP outside the TLS session and the proxy",
)
mutant(
    "http-interim-reply-taken-as-the-final-one",
    f"{_HTTP_PKG}/_builtin.py",
    "            if status == _client.CONTINUE:\n                return version, status, reason  # `begin()` skips its headers\n",
    "            if True:\n                return version, status, reason  # `begin()` skips its headers\n",
    (
        "tests/test_http_transport.py::test_the_built_in_transport_skips_interim_replies_and_returns_the_final_one",
        "tests/test_http_transport.py::test_an_interim_reply_is_never_the_previous_answer_of_the_next_request",
    ),
    "a 103 Early Hints is the reply, and the real one is read as the answer to the next request",
)
mutant(
    "http-interim-replies-not-counted",
    f"{_HTTP_PKG}/_builtin.py",
    "            if self._interim > MAX_INTERIM_REPLIES:\n",
    "            if False:\n",
    (
        "tests/test_http_transport.py::test_a_bounded_number_of_interim_replies_is_skipped",
        "tests/test_http_transport.py::test_an_endless_stream_of_100_continue_is_given_up_not_waited_out",
    ),
    "a server that answers with endless interim replies is waited on without limit",
)
mutant(
    "http-no-proxy-cidr-ignored",
    f"{_HTTP_PKG}/_proxies.py",
    '        if _in_no_proxy_network(host, chosen.get("no", "")):\n',
    "        if False:\n",
    "tests/test_http_proxy.py::test_a_cidr_block_in_no_proxy_sends_an_ip_literal_host_direct",
    "a request to a host inside a NO_PROXY block goes to the proxy, which sees its Authorization",
)
_PEER = "tests/test_http_peer_text.py"

mutant(
    "http-peer-text-not-escaped",
    f"{_HTTP_PKG}/_headers.py",
    '        char if char.isprintable() else char.encode("unicode_escape").decode("ascii")\n',
    "        char\n",
    f"{_PEER}::test_peer_text_escapes_what_a_terminal_would_act_on",
    "text from the peer keeps its control characters in an error message",
)
mutant(
    "http-reason-phrase-unescaped",
    "schemes/_http/_errors.py",
    '        reason = peer_text(response.reason or "")\n',
    '        reason = response.reason or ""\n',
    (
        f"{_PEER}::test_a_reason_phrase_is_shown_escaped",
        f"{_PEER}::test_a_long_reason_phrase_is_cut",
    ),
    "an HTTP error's reason phrase reaches the message as the server sent it",
)
mutant(
    "git-reason-phrase-unescaped",
    "schemes/_gitrepo.py",
    '        reason = peer_text(response.reason or "")\n',
    '        reason = response.reason or ""\n',
    f"{_PEER}::test_the_reason_phrase_of_a_git_api_reply_is_shown_escaped",
    "a git API error's reason phrase reaches the message as the server sent it",
)
mutant(
    "http-refused-redirect-location-unbounded",
    f"{_HTTP_PKG}/_follow.py",
    '    where = peer_text(shown(location), 200) if location else "(none)"\n',
    '    where = shown(location) if location else "(none)"\n',
    f"{_PEER}::test_a_redirect_that_is_refused_is_shown_cut_and_with_an_escaped_reason",
    "a refused redirect's message holds the whole Location",
)
mutant(
    "http-redirect-reask-forgets-the-origin",
    "schemes/_http/_backend.py",
    "            method, location, sent, None, None, stream, timeout, first=url\n",
    "            method, location, sent, None, None, stream, timeout, first=None\n",
    (
        "tests/test_http_redirect_origin.py::test_a_redirect_to_another_origin_does_not_carry_authorization",
        "tests/test_http_redirect_origin.py::test_a_patch_mode_append_asks_the_other_origin_without_authorization",
    ),
    "stat() and what is built on it re-ask the redirect target as if it were the first origin, with Authorization",
)
mutant(
    "http-redirect-reask-sends-the-backend-headers-again",
    "schemes/_http/_follow.py",
    "        if origin(current) != home:\n",
    "        if origin(current) != origin(url):\n",
    "tests/test_http_redirect_origin.py::test_a_redirect_to_another_origin_does_not_carry_authorization",
    "a re-request compares the redirect target with itself instead of with the origin it was asked for",
)
mutant(
    "http-unusable-location-reaches-the-transport",
    f"{_HTTP_PKG}/_follow.py",
    "        check_url(absolute)\n        return absolute\n",
    "        return absolute\n",
    "tests/test_http_redirects.py::test_a_location_the_url_check_refuses_is_oserror_never_valueerror",
    "a Location the URL check refuses is sent on, and its ValueError reaches the caller",
)
mutant(
    "http-redirect-without-a-usable-location-is-the-reply",
    f"{_HTTP_PKG}/_follow.py",
    '        if location is None:\n            _discard(resp)\n            raise refused_redirect(method, current, resp, None, "no usable Location")\n        if hops >= MAX_REDIRECTS:',
    "        if location is None:\n            return resp\n        if hops >= MAX_REDIRECTS:",
    "tests/test_http_redirects.py::test_a_location_that_is_not_an_http_url_is_a_refused_redirect",
    "a redirect with an unusable Location reads as the answer itself",
)
_LIMITS = "tests/test_http_reply_limits.py"

mutant(
    "http-reply-limit-not-applied",
    f"{_HTTP_PKG}/_response.py",
    "            if limit is not None and len(data) > limit:\n",
    "            if False:\n",
    (
        f"{_LIMITS}::test_a_propfind_reply_over_the_limit_is_efbig_counted_in_decoded_bytes",
        f"{_LIMITS}::test_a_git_api_reply_over_the_limit_is_efbig_and_a_file_is_not_limited",
        f"{_LIMITS}::test_the_backend_reads_a_reply_whole_only_up_to_the_limit",
    ),
    "a reply read whole is held in memory however long it decodes to",
)
mutant(
    "http-dropped-reply-read-without-a-bound",
    f"{_HTTP_PKG}/_status.py",
    "            remaining -= len(chunk)\n",
    "            pass\n",
    f"{_LIMITS}::test_the_reply_to_a_write_is_dropped_and_its_connection_is_not_kept",
    "the body of a reply nobody looks at is read to its end, however long",
)
mutant(
    "dav-propfind-reply-read-unbounded",
    "schemes/_dav.py",
    "        body = _read_limited(resp, _settings.MAX_LISTING_BYTES, self)\n",
    "        body = resp.read()\n",
    f"{_LIMITS}::test_a_propfind_reply_over_the_limit_is_efbig_counted_in_decoded_bytes",
    "a PROPFIND reply is read whole whatever its size",
)
mutant(
    "git-json-reply-read-unbounded",
    f"{_HTTP_PKG}/_status.py",
    "    return _json.loads(read_limited(resp, limit, what))",
    "    return _json.loads(resp.read())",
    f"{_LIMITS}::test_a_git_api_reply_over_the_limit_is_efbig_and_a_file_is_not_limited",
    "a git API's JSON reply is read whole whatever its size",
)
mutant(
    "http-backend-buffers-without-a-cap",
    "schemes/_http/_backend.py",
    "            resp._buffered(limit, _too_large(_follow.shown(url), limit))\n",
    "            resp._buffered()\n",
    f"{_LIMITS}::test_the_backend_reads_a_reply_whole_only_up_to_the_limit",
    "request(stream=False) reads a reply to its end whatever its size",
)
mutant(
    "http-exchange-runs-under-the-connect-timeout",
    f"{_HTTP_PKG}/_builtin.py",
    "                sock.settimeout(read_timeout)\n",
    "                sock.settimeout(connect_timeout)\n",
    "tests/test_http_transport.py::test_a_server_that_never_answers_is_a_timeout_after_the_read_timeout",
    "the wait for a reply is bounded by the connect half of the timeout",
)
_BODY = "tests/test_http_body.py"
mutant(
    "http-body-length-ignores-the-position",
    f"{_HTTP_PKG}/_body.py",
    "        return max(0, end - here)\n",
    "        return max(0, end)\n",
    (
        f"{_BODY}::test_a_bytes_io_part_way_sends_what_is_left_under_that_length",
        f"{_BODY}::test_an_open_file_part_way_sends_what_is_left_under_that_length",
    ),
    "a file read from the middle is sent under the length of the whole file",
)
mutant(
    "http-body-sent-past-its-length",
    f"{_HTTP_PKG}/_body.py",
    "        want = self._left if amount is None or amount < 0 else min(amount, self._left)\n",
    "        want = self._left if amount is None or amount < 0 else amount\n",
    (
        f"{_BODY}::test_a_file_that_grew_after_it_was_measured_sends_only_the_length_it_stated",
        f"{_BODY}::test_a_length_the_caller_set_cuts_a_longer_body_at_that_length",
    ),
    "a body longer than its Content-Length sends the rest into the next request",
)
mutant(
    "http-body-short-of-its-length-is-not-an-error",
    f"{_HTTP_PKG}/_body.py",
    "        if not chunk:\n            raise OSError(\n",
    "        if False:\n            raise OSError(\n",
    (
        f"{_BODY}::test_a_file_that_ends_before_the_length_it_stated_is_an_error",
        f"{_BODY}::test_a_generator_that_ends_before_the_length_the_caller_set_is_an_error",
    ),
    "a body that ends before its Content-Length leaves the server waiting for the rest",
)
mutant(
    "http-length-larger-than-the-body-is-sent",
    f"{_HTTP_PKG}/_body.py",
    "        if known is not None and declared > known:\n",
    "        if False:\n",
    f"{_BODY}::test_a_length_larger_than_a_body_whose_size_is_known_is_refused",
    "a Content-Length larger than a file or list is sent and the upload stalls",
)
