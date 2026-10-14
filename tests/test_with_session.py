"""The `requests` transport as a path asks for it: `with_session()` builds the
transport that an installed distribution declares in the entry-point group
`pathapi.http_transports`, and raises `ImportError` naming the
distribution when there is none."""

from __future__ import annotations

import pytest

from fake_distribution import install, run
from pathapi.http import _transports
from uripath.schemes import HTTPURIPath

REQUESTS_MESSAGE = (
    "the 'requests' HTTP transport is provided by the pathapi-requests "
    "distribution: pip install pathapi-requests"
)


@pytest.fixture
def nothing_declared(monkeypatch):
    """No installed distribution declares a transport."""
    monkeypatch.setattr(_transports, "_declared", lambda: {})


def test_with_session_without_the_distribution_names_it(nothing_declared):
    with pytest.raises(ImportError) as raised:
        HTTPURIPath("http://h/x").with_session(object(), write_method="POST")
    assert str(raised.value) == REQUESTS_MESSAGE


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
"""


@pytest.fixture
def provider(tmp_path):
    return install(
        tmp_path,
        "fake-transports",
        {"pathapi.http_transports": {"requests": "fake_transports:Fake"}},
        {"fake_transports": PROVIDER},
    )


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


def test_the_variable_names_the_installed_transport_a_path_sends_through(provider):
    found = run(
        """
        import json
        from uripath.schemes import HTTPBackend
        with HTTPBackend() as backend:
            transport = backend.transport
            print(json.dumps([type(transport).__name__, transport.closed]))
        """,
        provider,
        env={"PATHAPI_HTTP_TRANSPORT": "requests"},
    )
    assert found == ["Fake", 0]
