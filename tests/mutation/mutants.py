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

# --- guards of the library ---------------------------------------------------
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
    "        scheme, userinfo, host, port = _source_parts(self, True)\n",
    "        scheme, userinfo, host, port = _source_parts(self, False)\n",
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
    "http-write-stream-uploads-before-it-is-ready",
    "schemes/_http/_streams.py",
    "            if self._ready:\n                self._upload(self.getvalue())\n",
    "            if True:\n                self._upload(self.getvalue())\n",
    "tests/test_http_writes.py",
    "a write stream whose constructor raised uploads its half-built buffer when collected",
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
    "                    *_BUILTIN_SCHEMES,\n                    *_declared_entry_points(),\n",
    "",
    (
        f"{_SCHEME_TESTS}::test_schemes_lists_every_built_in_name_without_importing_its_module",
        f"{_SCHEME_TESTS}::test_schemes_lists_an_entry_point_whose_module_is_not_imported",
    ),
    "schemes() lists only the classes already imported",
)
_UNREGISTERED = "tests/test_unregistered_scheme.py"
mutant(
    "scheme-class-of-an-unregistered-scheme-suggests-nothing",
    "schemes/_path.py",
    '                + "; "\n                + suggestions(name)\n',
    "",
    f"{_UNREGISTERED}::test_the_scheme_class_of_an_unregistered_scheme_suggests_names_to_look_for",
    "the UnsupportedSchemeError of scheme_class() has no names to look for",
)
mutant(
    "a-scheme-without-a-class-is-a-plain-path",
    "schemes/_path.py",
    "            if cls is URIPath and uri.source.scheme and schemesmap is None:\n",
    "            if False:\n",
    f"{_UNREGISTERED}::test_an_operation_that_needs_the_server_names_what_to_look_for",
    "I/O on a path of a scheme without a class raises NotImplementedError again",
)
mutant(
    "suggestions-keep-the-whole-scheme",
    "schemes/_unregistered.py",
    '    name = scheme.lower().split("+", 1)[0]\n',
    "    name = scheme.lower()\n",
    f"{_UNREGISTERED}::test_the_name_is_the_part_of_the_scheme_before_the_first_plus",
    "svn+https suggests svn+httppath",
)
mutant(
    "an-unregistered-scheme-shows-its-user-name",
    "schemes/_path.py",
    "    return found is None or bool(found._SECRET_USERINFO)\n",
    "    return found is not None and bool(found._SECRET_USERINFO)\n",
    f"{_UNREGISTERED}::test_the_source_of_an_unregistered_scheme_shows_no_userinfo",
    "str() of the Source of an unregistered scheme shows a token",
)
mutant(
    "a-class-that-says-its-user-name-is-a-secret-is-not-believed",
    "schemes/_path.py",
    "    return found is None or bool(found._SECRET_USERINFO)\n",
    "    return found is None\n",
    f"{_UNREGISTERED}::test_a_class_says_that_its_user_name_is_a_secret",
    "a registered class cannot hide its user name",
)
mutant(
    "a-class-that-fails-to-load-shows-its-user-name",
    "schemes/_path.py",
    "    except Exception:\n        return True\n",
    "    except Exception:\n        return False\n",
    f"{_UNREGISTERED}::test_a_class_that_fails_to_load_hides_the_userinfo",
    "a lookup that fails fails open",
)
mutant(
    "with-session-ignores-the-installed-transport",
    "schemes/_http/_path.py",
    '            get_transport("requests")(session, **requests_args),\n',
    "            None,\n",
    "tests/test_with_session.py::test_with_session_sends_through_the_installed_transport",
    "with_session() sends with the built-in transport and drops the session",
)
mutant(
    "scheme-registry-same-qualified-name-in-another-module-is-the-same-class",
    "schemes/_registry.py",
    "    return a.__module__ == b.__module__ and a.__qualname__ == b.__qualname__\n",
    "    return a.__qualname__ == b.__qualname__\n",
    f"{_SCHEME_TESTS}::test_a_class_of_the_same_qualified_name_in_another_module_is_still_refused",
    "a class of another module takes a scheme from a class that has the same name",
)


# --- http paths: the guards above the transport ----------------------------------

_PEER = "tests/test_http_peer_text.py"

_LIMITS = "tests/test_http_reply_limits.py"

mutant(
    "dav-propfind-reply-read-unbounded",
    "schemes/_dav.py",
    "        body = read_limited(resp, self)\n",
    "        body = resp.read()\n",
    f"{_LIMITS}::test_a_propfind_reply_over_the_limit_is_efbig_counted_in_decoded_bytes",
    "a PROPFIND reply is read whole whatever its size",
)

# --- query and fragment through a derivation ----------------------------------

_DERIVATION = "tests/test_uri_derivation_query.py"
_LISTING = "tests/test_http_listing.py"
mutant(
    "destination-takes-the-sources-query",
    "_uri.py",
    "        return parent._from_parsed_parts(parent.source, parent.path, None, None)\n",
    "        return parent\n",
    (
        f"{_DERIVATION}::test_a_str_destination_takes_neither_the_query_nor_the_fragment_of_its_source",
        f"{_LISTING}::test_rename_destination_carries_the_targets_query_not_the_sources",
    ),
    "a rename or copy destination named by a string carries the source's signature",
)
mutant(
    "http-listed-child-takes-the-index-query",
    "schemes/_http/_path.py",
    '        child = self._from_parsed_parts(self.source, directory + name, "", "", **kwargs)\n',
    "        child = self._from_parsed_parts(\n"
    "            self.source, directory + name, self.query, self.fragment, **kwargs\n"
    "        )\n",
    (
        f"{_LISTING}::test_http_joined_child_keeps_the_directory_query_but_a_listed_one_has_none",
        f"{_LISTING}::test_dav_joined_child_keeps_the_collection_query_but_a_listed_one_has_none",
    ),
    "a listed file is requested with the query that shaped its index",
)
mutant(
    "join-drops-the-query",
    "_uri.py",
    "        return self._from_parsed_parts(self.source, path, self.query, self.fragment)\n\n    def _join_children",
    '        return self._from_parsed_parts(self.source, path, "", "")\n\n    def _join_children',
    f"{_DERIVATION}::test_a_path_only_derivation_keeps_the_query_and_the_fragment",
    "a token in the query stops following the names joined onto it",
)

# --- file: text and == with text -----------------------------------------------

_FILE_TEXT = "tests/test_file_uri_text.py"
mutant(
    "empty-authority-is-dropped",
    "source/_source.py",
    "    host = source.host if source.host is not None else None\n",
    "    host = source.host if source.host else None\n",
    (
        f"{_FILE_TEXT}::test_a_file_uri_is_written_back_as_it_was_read",
        f"{_FILE_TEXT}::test_a_file_path_is_written_as_pathlib_writes_it",
    ),
    "file:///x is written file:/x and no longer equals the text pathlib gives",
)
mutant(
    "uri-equals-text-as-written",
    "_uri.py",
    "                uri = URI(other)._identity()\n",
    "                uri = other\n",
    f"{_FILE_TEXT}::test_a_uri_equals_the_text_that_names_it",
    "a URI is false against the canonical text of its own file",
)

# --- data: URIs ---------------------------------------------------------------

_DATA = "tests/test_data_uri.py"
mutant(
    "data-uri-payload-is-sliced-into-names",
    "_uri.py",
    '        if self.source.scheme == "data":\n            raise NotImplementedError(\n',
    "        if False:\n            raise NotImplementedError(\n",
    f"{_DATA}::test_the_pure_path_derivations_of_a_data_uri_raise",
    "a join or a parent of a data: URI cuts the payload and names another file",
)
mutant(
    "data-uri-text-ignores-the-declared-charset",
    "schemes/_data.py",
    "            encoding = self.charset\n",
    "            encoding = None\n",
    f"{_DATA}::test_text_is_read_in_the_charset_the_uri_declares",
    "read_text() decodes a data: payload with the locale instead of its declared charset",
)

# --- a write block that raised ------------------------------------------------

_WRITES = "tests/test_http_writes.py"
mutant(
    "upload-stream-sends-after-a-failed-block",
    "schemes/_http/_streams.py",
    "        self._ready = False\n        if not self.closed:\n            self.truncate(0)\n",
    "        pass\n",
    (
        f"{_WRITES}::test_a_failed_write_block_sends_no_put_and_keeps_the_file",
        f"{_WRITES}::test_a_failed_write_block_does_not_create_the_file",
    ),
    "a producer that fails half way replaces a complete remote file with the partial one",
)
mutant(
    "upload-stream-without-the-discard-mixin",
    "schemes/_http/_streams.py",
    "class _UploadStream(_providers.DiscardOnError, _io.BytesIO):\n",
    "class _UploadStream(_io.BytesIO):\n",
    f"{_WRITES}::test_a_failed_write_block_sends_no_put_and_keeps_the_file",
    "the stream is closed, and so uploaded, by the block that raised through it",
)

# --- the case of a host -------------------------------------------------------

_HOST = "tests/test_host_case.py"
mutant(
    "uri-equality-reads-the-case-of-the-host",
    "_uri.py",
    "        host = fold_host(source.host)\n        if host == source.host:\n",
    "        host = source.host\n        if host == source.host:\n",
    f"{_HOST}::test_uris_that_differ_in_the_case_of_the_host_are_equal",
    "a file is not recognised as itself when its host is spelled in another case",
)
mutant(
    "same-authority-reads-the-case-of-the-host",
    "source/_source.py",
    "        str(host).lower() if host else None,\n",
    "        str(host) if host else None,\n",
    (
        f"{_HOST}::test_the_same_authority_is_decided_without_regard_to_the_case_of_the_host",
        f"{_HOST}::test_a_rename_within_one_server_is_not_a_move_to_another",
    ),
    "a backend or a rename stops following a host spelled in another case",
)
mutant(
    "containment-reads-the-case-of-the-host",
    "_uri.py",
    "            _same_authority(other.source, self.source)\n",
    "            (other.source == self.source)\n",
    f"{_HOST}::test_relative_to_and_containment_do_not_depend_on_the_case_of_the_host",
    "a copy of a directory into itself is not recognised when the host is spelled in another case",
)
mutant(
    "localhost-reads-the-case",
    "source/_source.py",
    '        host = fold_host(self.host)\n        if not host or host == "localhost":\n',
    '        host = self.host\n        if not host or host == "localhost":\n',
    f"{_HOST}::test_localhost_is_this_machine_in_any_case",
    "LOCALHOST is looked up as a remote name",
)

# --- constructor keywords -----------------------------------------------------

mutant(
    "constructor-accepts-a-misspelt-backend",
    "_uri.py",
    "            if name not in accepted:\n",
    "            if False:\n",
    "tests/test_uri_constructor_options.py::test_an_unknown_keyword_argument_is_a_type_error_naming_it",
    "a misspelt backend= is ignored and the path uses the default backend and ambient credentials",
)

# --- the command line: nothing is deleted or replaced unless it is asked for --------

_CLI = "tests/test_cli.py"
_TOOLS = "tests/test_cli_surface.py"

mutant(
    "cli-rm-removes-a-tree-without-recursive",
    "cli/rm.py",
    "            recursive=self.recursive,\n",
    "            recursive=True,\n",
    (
        f"{_CLI}::test_rm_removes_a_file_and_refuses_a_directory_with_content",
        f"{_TOOLS}::test_a_tool_call_removes_a_tree_only_when_it_says_recursive",
    ),
    "uripath rm deletes a directory with everything in it when --recursive was not given",
)
mutant(
    "cli-rm-succeeds-on-a-missing-path",
    "cli/rm.py",
    "            missing_ok=self.missing_ok,\n",
    "            missing_ok=True,\n",
    f"{_CLI}::test_rm_of_a_missing_path_fails_unless_told_to_accept_it",
    "uripath rm reports success for a path that was never there when --missing-ok was not given",
)
mutant(
    "cli-sync-removes-what-the-source-lacks",
    "cli/sync.py",
    "            remove_missing=self.remove_missing,\n",
    "            remove_missing=True,\n",
    (
        f"{_CLI}::test_sync_keeps_what_the_source_lacks_unless_told_to_remove_it",
        f"{_TOOLS}::test_a_tool_call_deletes_from_the_target_only_when_it_says_remove_missing",
    ),
    "uripath sync deletes entries of the target that the source lacks when --remove-missing was not given",
)
mutant(
    "cli-sync-dry-run-changes-the-target",
    "cli/sync.py",
    "        ).sync(as_path(self.source), as_path(self.target), dry_run=self.dry_run)\n",
    "        ).sync(as_path(self.source), as_path(self.target), dry_run=False)\n",
    f"{_CLI}::test_sync_dry_run_prints_planned_changes_and_changes_nothing",
    "uripath sync --dry-run makes the changes it only meant to print",
)
mutant(
    "cli-sync-goes-into-a-mount-point-it-was-told-not-to",
    "cli/sync.py",
    "            follow_mounts=self.follow_mounts,\n",
    "            follow_mounts=True,\n",
    f"{_CLI}::test_sync_no_follow_mounts_fails_on_a_mount_point_and_leaves_it",
    "uripath sync --no-follow-mounts writes into a mount point inside the target",
)
mutant(
    "cli-cp-replaces-an-existing-target-by-default",
    "cli/cp.py",
    "            overwrite=self.overwrite,\n            follow_symlinks",
    "            overwrite=True,\n            follow_symlinks",
    f"{_CLI}::test_cp_refuses_an_existing_target_without_overwrite",
    "uripath cp replaces an existing target when --overwrite was not given",
)
mutant(
    "cli-cp-stream-replaces-an-existing-target-by-default",
    "cli/cp.py",
    "                exclusive=not self.overwrite,\n",
    "                exclusive=False,\n",
    f"{_CLI}::test_cp_stdin_refuses_an_existing_target_without_overwrite",
    "uripath cp - TARGET truncates an existing TARGET when --overwrite was not given",
)
mutant(
    "cli-cp-recursive-with-a-stream",
    "cli/cp.py",
    "        if streamed and self.recursive:\n",
    "        if False:\n",
    f"{_CLI}::test_cp_recursive_with_dash_is_a_wrong_invocation",
    "uripath cp -r with - is accepted and copies a stream as if it were a tree",
)
mutant(
    "cli-tool-reads-the-standard-input-of-the-server",
    "cli/_common.py",
    '    if running_mode() == "mcp":\n',
    "    if False:\n",
    f"{_TOOLS}::test_a_tool_cannot_read_the_standard_input_the_server_listens_on",
    "a command served as a tool reads the requests of the protocol as if they were its input",
)
mutant(
    "copy-stream-exclusive-create-replaces-the-target",
    "_transfer.py",
    '    with _path_of(target).open("xb" if exclusive else "wb") as writer:\n',
    '    with _path_of(target).open("wb") as writer:\n',
    (
        "tests/test_copy_stream.py::test_exclusive_refuses_an_existing_target_and_keeps_it",
        f"{_CLI}::test_cp_stdin_refuses_an_existing_target_without_overwrite",
    ),
    "copy_stream(exclusive=True) truncates an existing target path",
)
mutant(
    "copy-stream-reports-a-broken-connection-of-a-target-path-as-output-closed",
    "_transfer.py",
    '"wb") as writer:\n        _shutil.copyfileobj(reader, writer, chunk_size)\n',
    '"wb") as writer:\n        _shutil.copyfileobj(reader, _PipeWriter(writer), chunk_size)\n',
    "tests/test_copy_stream.py::test_a_broken_pipe_of_a_target_path_is_not_output_closed",
    "a connection that breaks while a path is written is taken for the reader of the output going away",
)
mutant(
    "delegated-error-names-the-core-path",
    "schemes/_delegate.py",
    "            _relabel(error, names)\n            raise\n",
    "            raise\n",
    "tests/test_delegating_uri_path.py::test_an_error_of_the_core_path_names_the_uri_and_not_the_core_path",
    "an OSError of the core path reaches the caller naming the core path, not the URI",
)
mutant(
    "delegated-extra-pairs-are-ignored",
    "schemes/_delegate.py",
    "            names = {**({core: str(self)} if core else {}), **dict(extra)}\n",
    "            names = {core: str(self)} if core else {}\n",
    "tests/test_delegating_uri_path.py::test_delegated_extra_pairs_rename_the_text_of_a_hand_written_call",
    "a second path in an error of a hand-written call keeps the core name",
)
mutant(
    "unclosed-upload-stream-is-sent-at-collection",
    "schemes/_http/_streams.py",
    "    def _holds_uncommitted(self):\n        return self._ready\n",
    "    def _holds_uncommitted(self):\n        return False\n",
    (
        "tests/test_http_unclosed_upload.py::test_an_unclosed_binary_upload_is_discarded_at_collection",
        "tests/test_http_unclosed_upload.py::test_an_unclosed_text_upload_is_discarded_at_collection",
    ),
    "a write stream that the collector finalizes unclosed uploads what it holds",
)
mutant(
    "half-built-upload-stream-warns-at-collection",
    "schemes/_http/_streams.py",
    "    def _holds_uncommitted(self):\n        return self._ready\n",
    "    def _holds_uncommitted(self):\n        return True\n",
    "tests/test_http_writes.py::test_append_open_whose_read_fails_sends_no_upload",
    "a stream whose constructor raised warns and discards when collected",
)
