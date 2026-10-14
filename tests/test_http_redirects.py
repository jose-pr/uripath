"""Redirects and credentials above a transport, as a path meets them: the
credentials in a URL are an `Authorization` that a redirect to another scheme,
host or port leaves behind, and a `Location` that cannot be requested is an
`OSError` of the operation, whichever transport sends the requests. The rules
themselves are `pathapi.http`'s."""

import errno

import pytest

from http_wire import Reply, Wire, response
from uripath import URIPath
from uripath.schemes import HTTPBackend


def redirect(location, status=302):
    return response(status, {"Location": location}, reason="Found")


def test_authorization_from_url_userinfo_is_dropped_the_same_way(http_transport):
    with Wire() as elsewhere:
        with Wire(lambda r: redirect(elsewhere.url + "/landing")) as wire:
            backend = HTTPBackend(http_transport)
            backend.request(
                "GET", f"http://alice:s3cr3t@127.0.0.1:{wire.port}/s"
            ).read()
    assert wire.requests[0].header("Authorization").startswith("Basic ")
    assert elsewhere.requests[0].header("Authorization") is None


# --- a Location the URL check refuses ----------------------------------------------

REFUSED_LOCATIONS = [
    "http://127.0.0.1:99999/x",  # a port out of range
    "http://127.0.0.1:port/x",  # a port that is not a number
    "http://a。。b/x",  # a host name with an empty label
    "http://" + "é" * 70 + "/x",  # a label too long to be a name
    "http://[::1/x",  # an unclosed address
]


@pytest.mark.parametrize("location", REFUSED_LOCATIONS)
@pytest.mark.parametrize("operation", ["read_bytes", "stat", "iterdir", "is_dir"])
def test_a_location_the_url_check_refuses_is_oserror_never_valueerror(
    http_transport_kind, location, operation
):
    raw = (
        "HTTP/1.1 302 Found\r\nLocation: " + location + "\r\nContent-Length: 0\r\n\r\n"
    ).encode("utf-8")
    with Wire(lambda r: Reply(raw)) as wire:
        path = URIPath(wire.url + "/f")
        try:
            outcome = getattr(path, operation)()
            if operation == "iterdir":
                list(outcome)
        except ValueError:
            raise AssertionError("a ValueError escaped") from None
        except OSError as error:
            # The refused reply is named by its status; `requests` reads a
            # Location it cannot parse before this library sees the reply.
            assert error.errno == errno.EIO
            assert "HTTP 302" in str(error) or "could not be read" in str(error)
        else:
            assert operation == "is_dir" and outcome is False
    assert len(wire.requests) in (1, 2)  # the slash form is asked for first


@pytest.mark.parametrize("location", REFUSED_LOCATIONS)
def test_a_walk_over_a_refused_location_ends_with_the_oserror_it_catches(
    http_transport_kind, location
):
    raw = (
        "HTTP/1.1 302 Found\r\nLocation: " + location + "\r\nContent-Length: 0\r\n\r\n"
    ).encode("utf-8")
    with Wire(lambda r: Reply(raw)) as wire:
        # `walk()` and `exists()` meet OSError as an unreadable directory.
        assert list(URIPath(wire.url + "/d/").walk()) == []
        assert URIPath(wire.url + "/d/").exists() is False
