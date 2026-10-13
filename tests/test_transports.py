"""The HTTP transports a distribution can provide: listed without importing
them, loaded by name from the `uripath.http_transports` entry-point group, and
chosen by `with_session()`, a `RepoBackend` and `URIPATH_HTTP_TRANSPORT`."""

from __future__ import annotations

import pytest

from fake_distribution import install, run
from uripath import transports
from uripath.schemes import HTTPBackend, HTTPTransport, HTTPURIPath, RepoBackend

REQUESTS_MESSAGE = (
    "the 'requests' HTTP transport is provided by the uripath-http-requests "
    "distribution: pip install uripath-http-requests"
)


@pytest.fixture
def nothing_declared(monkeypatch):
    """No installed distribution declares a transport."""
    monkeypatch.setattr(transports, "_declared", lambda: {})


class _Entry:
    def __init__(self, name, target):
        self.name = name
        self._target = target

    def load(self):
        return self._target


def test_the_built_in_transport_is_listed_with_the_ones_provided_elsewhere(
    nothing_declared,
):
    assert transports.names() == ("builtin", "requests")


def test_an_entry_of_the_group_is_listed(monkeypatch):
    monkeypatch.setattr(
        transports, "_declared", lambda: {"zeta": _Entry("zeta", object)}
    )
    assert transports.names() == ("builtin", "requests", "zeta")


def test_the_built_in_transport_needs_no_entry_point(nothing_declared):
    assert transports.get("builtin") is HTTPTransport


def test_an_entry_point_cannot_replace_the_built_in_transport(monkeypatch):
    class Other:
        pass

    monkeypatch.setattr(
        transports, "_declared", lambda: {"builtin": _Entry("builtin", Other)}
    )
    assert transports.get("builtin") is HTTPTransport


def test_a_declared_transport_is_loaded_by_name(monkeypatch):
    class Other:
        pass

    monkeypatch.setattr(
        transports, "_declared", lambda: {"other": _Entry("other", Other)}
    )
    assert transports.get("other") is Other


def test_an_entry_that_is_not_a_class_is_a_type_error(monkeypatch):
    monkeypatch.setattr(
        transports, "_declared", lambda: {"odd": _Entry("odd", "not callable")}
    )
    with pytest.raises(TypeError, match="'odd'"):
        transports.get("odd")


def test_a_transport_provided_elsewhere_that_is_not_installed_names_the_distribution(
    nothing_declared,
):
    with pytest.raises(ImportError) as raised:
        transports.get("requests")
    assert str(raised.value) == REQUESTS_MESSAGE
    assert raised.value.name == "uripath_http_requests"


@pytest.mark.parametrize("name", ["", "Requests", "BUILTIN", "urllib3", None, 3])
def test_a_name_that_is_not_a_transport_is_a_value_error_naming_the_choices(
    nothing_declared, name
):
    with pytest.raises(ValueError) as raised:
        transports.get(name)
    assert "expected one of 'builtin', 'requests'" in str(raised.value)


def test_with_session_without_the_distribution_names_it(nothing_declared):
    with pytest.raises(ImportError) as raised:
        HTTPURIPath("http://h/x").with_session(object(), write_method="POST")
    assert str(raised.value) == REQUESTS_MESSAGE


@pytest.mark.parametrize("arguments", [{"session": object()}, {"verify": False}])
def test_a_repository_backend_given_a_session_names_the_distribution(
    nothing_declared, arguments
):
    with pytest.raises(ImportError) as raised:
        RepoBackend(**arguments)
    assert str(raised.value) == REQUESTS_MESSAGE


def test_the_requests_transport_asked_for_by_the_environment_names_the_distribution(
    nothing_declared, monkeypatch
):
    monkeypatch.setenv("URIPATH_HTTP_TRANSPORT", "requests")
    with HTTPBackend() as backend:
        with pytest.raises(ImportError) as raised:
            backend.transport
    assert str(raised.value) == REQUESTS_MESSAGE


def test_a_session_and_a_transport_together_are_refused(monkeypatch):
    monkeypatch.setattr(
        transports, "_declared", lambda: {"requests": _Entry("requests", object)}
    )
    with pytest.raises(TypeError):
        RepoBackend(transport=object(), session=object())


# --- a distribution that is installed ---------------------------------------

PROVIDER = """
    class Fake:
        def __init__(self, session=None, **arguments):
            self.session = session
            self.arguments = arguments
            self.closed = 0

        def send(self, method, url, *, headers, body=None, timeout, stream=False):
            raise NotImplementedError

        def close(self):
            self.closed += 1

    class Other(Fake):
        pass

    class NotBuiltin(Fake):
        pass
"""


@pytest.fixture
def provider(tmp_path):
    return install(
        tmp_path,
        "fake-transports",
        {
            "uripath.http_transports": {
                "requests": "fake_transports:Fake",
                "other": "fake_transports:Other",
                "builtin": "fake_transports:NotBuiltin",
            }
        },
        {"fake_transports": PROVIDER},
    )


def test_an_installed_distribution_is_listed_without_being_imported(provider):
    found = run(
        """
        import json, sys
        from uripath import transports
        print(json.dumps([list(transports.names()), "fake_transports" in sys.modules]))
        """,
        provider,
    )
    assert found == [["builtin", "other", "requests"], False]


def test_an_installed_distribution_provides_the_transport_by_name(provider):
    found = run(
        """
        import json
        from uripath import transports
        import fake_transports
        print(json.dumps([
            transports.get("requests") is fake_transports.Fake,
            transports.get("other") is fake_transports.Other,
            transports.get("builtin").__name__,
        ]))
        """,
        provider,
    )
    assert found == [True, True, "HTTPTransport"]


def test_with_session_sends_through_the_installed_transport(provider):
    found = run(
        """
        import json
        from uripath.schemes import HTTPURIPath
        session = object()
        path = HTTPURIPath("http://127.0.0.1:1/x").with_session(
            session, write_method="POST", append_mode="patch",
            headers={"X-A": "1"}, timeout=3, verify=False,
        )
        transport = path.backend.transport
        print(json.dumps([
            type(transport).__name__,
            transport.session is session,
            transport.arguments,
            path.backend.timeout,
            path.backend.headers,
            path.backend.write_method,
            path.backend.append_mode,
        ]))
        """,
        provider,
    )
    assert found == [
        "Fake",
        True,
        {"verify": False},
        3,
        {"X-A": "1"},
        "POST",
        "patch",
    ]


def test_a_repository_backend_builds_the_installed_transport_from_a_session(provider):
    found = run(
        """
        import json
        from uripath.schemes import RepoBackend
        session = object()
        backend = RepoBackend(session=session, verify=False)
        print(json.dumps([
            type(backend.transport).__name__,
            backend.transport.session is session,
            backend.transport.arguments,
        ]))
        """,
        provider,
    )
    assert found == ["Fake", True, {"verify": False}]


@pytest.mark.parametrize("name, cls", [("requests", "Fake"), ("other", "Other")])
def test_the_variable_names_an_installed_transport(provider, name, cls):
    found = run(
        """
        import json
        from uripath.schemes import HTTPBackend
        with HTTPBackend() as backend:
            transport = backend.transport
            print(json.dumps([type(transport).__name__, transport.closed]))
        """,
        provider,
        env={"URIPATH_HTTP_TRANSPORT": name},
    )
    assert found == [cls, 0]


def test_a_value_the_variable_cannot_resolve_names_the_choices(provider):
    found = run(
        """
        import json
        from uripath.schemes import HTTPBackend
        try:
            HTTPBackend().transport
        except ValueError as error:
            print(json.dumps(str(error)))
        """,
        provider,
        env={"URIPATH_HTTP_TRANSPORT": "Other"},
    )
    assert found == (
        "URIPATH_HTTP_TRANSPORT='Other' is not an HTTP transport "
        "(expected one of 'builtin', 'other', 'requests')"
    )
