import pytest

from uripath.source import Source


def test_bool_false_when_all_empty():
    assert not Source(None, None, None, None)
    assert not Source("", "", "", None)


def test_bool_true_when_any_set():
    assert Source("http", None, None, None)
    assert Source(None, None, "host", None)
    assert Source(None, None, None, 80)


def test_parsed_userinfo_splits_user_password():
    s = Source(None, "user:pass", None, None)
    assert s.parsed_userinfo() == ("user", "pass")


def test_parsed_userinfo_no_password():
    s = Source(None, "user", None, None)
    assert s.parsed_userinfo() == ("user", "")


def test_parsed_userinfo_empty():
    s = Source(None, None, None, None)
    assert s.parsed_userinfo() == ("", "")


def test_parse():
    s = Source.parse("http://user:pass@host:80")
    assert s.scheme == "http"
    assert s.host == "host"
    assert s.port == 80


def test_is_local_localhost():
    # `localhost` short-circuits before any DNS lookup.
    assert Source(None, None, "localhost", None).is_local()


def test_is_local_no_host():
    assert Source(None, None, None, None).is_local()
    assert Source(None, None, "", None).is_local()


def test_is_local_cached_same_result():
    s = Source(None, None, "localhost", None)
    assert s.is_local() is s.is_local()


def test_is_local_loopback_ip():
    # is_local() delegates the "is this address mine" check to
    # netimps.is_local_address(), which answers loopback without
    # requiring interface enumeration -- see netimps' own is_local_address
    # docstring.
    assert Source(None, None, "127.0.0.1", None).is_local()


def test_is_local_loopback_ipv6_literal():
    # Constructed via parse() (not a raw Source(...) string field) so
    # _decode_host() parses the bracketed literal into a real IPv6Address
    # -- the isinstance(host, str) branch in is_local() is then skipped
    # entirely.
    s = Source.parse("sftp://root@[::1]:22", strict=False)
    assert s.is_local()


def test_is_local_bare_ipv6_string_host():
    # A directly-constructed Source with host as a bare IPv6 str
    # (bypassing _decode_host()'s usual bracket-literal parsing -- a
    # supported construction pattern, Source's fields are public) must not
    # crash with socket.gaierror from an IPv4-only lookup. is_local() tries
    # netimps.try_parse() first, which handles any IP literal (v4 or v6)
    # directly, before falling through to hostname resolution.
    assert Source(None, None, "::1", None).is_local()


@pytest.mark.allow_network  # real resolution of this machine's own name
@pytest.mark.allow_program("nslookup")  # the resolver's last resort on POSIX
def test_is_local_own_hostname():
    # Exercises the real hostname->address resolution path end to end
    # (netimps.resolve()'s default backend chain), not just IP literals.
    # Skip if this environment's own hostname doesn't resolve at all --
    # e.g. an mDNS-only "*.local" name on a macOS CI runner. An empty
    # dnspython answer does not end resolve()'s chain, so the OS resolver is
    # asked too, but whether it answers is an environment question, not
    # something this test is meant to validate.
    import socket

    import netimps

    hostname = socket.gethostname()
    if not (netimps.resolve(hostname, "a") + netimps.resolve(hostname, "aaaa")):
        pytest.skip(f"{hostname!r} does not resolve in this environment")
    assert Source(None, None, hostname, None).is_local()


def test_is_local_false_for_nonresolving_hostname(monkeypatch):
    # A hostname that genuinely doesn't resolve anywhere returns False (a
    # definitive non-local answer) rather than raising --
    # netimps.resolve()'s contract is "always a list, empty on genuine
    # lookup failure, never an exception for a not-found name" (see
    # netimps.resolve()'s own docstring).
    #
    # The resolver is stubbed with that "not found" answer: a real lookup
    # of an .invalid name still queries the configured nameservers.
    import netimps

    queries = []

    def resolve(host, rdtype, *args, **kwargs):
        queries.append((host, rdtype))
        return []

    monkeypatch.setattr(netimps, "resolve", resolve)
    assert not Source(None, None, "this-host-does-not-exist.invalid", None).is_local()
    assert queries == [
        ("this-host-does-not-exist.invalid", "a"),
        ("this-host-does-not-exist.invalid", "aaaa"),
    ]


def test_is_local_own_interface_address():
    # A real address assigned to this machine (not just loopback) must
    # also be local -- exercises netimps.get_interfaces() enumeration,
    # not just the loopback fast path. `.ips` yields IPv4Interface/
    # IPv6Interface (CIDR-aware) objects -- `.ip` is the bare address
    # Source.host/is_local() actually deals in.
    import netimps

    own_ips = [
        str(ip.ip)
        for iface in netimps.get_interfaces()
        for ip in iface.ips
        if not ip.ip.is_link_local  # avoid a bare-form zone-id ambiguity
    ]
    assert own_ips, "test host has no non-link-local interface address"
    assert Source(None, None, own_ips[0], None).is_local()


def test_is_local_false_for_public_address():
    assert not Source(None, None, "8.8.8.8", None).is_local()


def test_getitem_by_name_and_index():
    s = Source("http", "u", "h", 80)
    assert s["scheme"] == "http"
    assert s[0] == "http"
    assert s[2] == "h"


def test_str_uses_uricompose():
    s = Source("http", None, "host", 80)
    assert str(s) == "http://host:80"


def test_network_guard_blocks_non_loopback_hosts(_block_non_loopback_network):
    # The autouse conftest guard: loopback works, anything else raises (and
    # would fail the test at teardown even if swallowed).
    import socket

    blocked = _block_non_loopback_network
    assert socket.getaddrinfo("127.0.0.1", 80)
    assert socket.getaddrinfo("localhost", 80)
    for call in (
        lambda: socket.getaddrinfo("example.com", 80),
        lambda: socket.create_connection(("192.0.2.1", 80), timeout=0.1),
    ):
        with pytest.raises(RuntimeError, match="non-loopback"):
            call()
    assert blocked == ["getaddrinfo 'example.com'", "getaddrinfo '192.0.2.1'"]
    blocked.clear()


# --- one name per conversion --------------------------------------------------


def test_parse_is_the_only_way_in_from_text_and_reveal_the_only_way_out_with_the_secret():
    assert not hasattr(Source, "from_str")
    assert not hasattr(Source, "as_str")
    source = Source.parse("sftp://root:secret@nas:22")
    assert str(source) == "sftp://root@nas:22"
    assert source.reveal() == "sftp://root:secret@nas:22"
    assert Source.parse(source.reveal()) == source


def test_parse_refuses_what_is_not_text_and_try_parse_does_too():
    for call in (Source.parse, Source.try_parse):
        for value in (None, b"http://h", 80, Source(None, None, "h", None)):
            with pytest.raises(TypeError, match="str"):
                call(value)


def test_try_parse_gives_none_or_the_default_for_text_that_does_not_parse():
    assert Source.try_parse("http://h:99999") is None
    assert Source.try_parse("http://[::1") is None
    assert Source.try_parse("http://h/some/path") is None
    fallback = Source("http", None, "fallback", None)
    assert Source.try_parse("http://h:99999", fallback) is fallback
    assert Source.try_parse("http://h/some/path", strict=False) == Source(
        "http", None, "h", None
    )


def test_try_parse_returns_what_parse_returns_for_text_that_parses():
    for text in ("http://u:p@h:80", "ftp://h", "file:", "//h"):
        assert Source.try_parse(text) == Source.parse(text)


def test_parse_takes_strict_by_keyword_only():
    with pytest.raises(TypeError):
        Source.parse("http://h/p", False)
