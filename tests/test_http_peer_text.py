"""Text from the other end that goes into an exception message of a path: a
reason phrase, a rate-limit header, an `href`. It is shown with its control
characters escaped and cut to a length, whichever transport sent the request."""

import xml.sax.saxutils

import pytest

from http_wire import Reply, Wire, response
from uripath import URIPath

pytestmark = pytest.mark.usefixtures("http_transport_kind")

ESC = "\x1b[31m"


def reply_with_reason(reason, status=500):
    raw = f"HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\n\r\n".encode("latin-1")
    return lambda request: Reply(raw)


def test_a_reason_phrase_is_shown_escaped(request):
    with Wire(reply_with_reason(f"Server {ESC}Error")) as wire:
        with pytest.raises(OSError) as excinfo:
            URIPath(wire.url + "/x").read_bytes()
    message = str(excinfo.value)
    assert "\x1b" not in message
    assert "Server \\x1b[31mError" in message


def test_a_long_reason_phrase_is_cut():
    with Wire(reply_with_reason("R" * 20000)) as wire:
        with pytest.raises(OSError) as excinfo:
            URIPath(wire.url + "/x").read_bytes()
    assert len(str(excinfo.value)) < 400


def test_the_href_of_a_failed_member_is_shown_escaped_and_few_are_listed():
    members = "".join(
        f"<D:response><D:href>/d/%1B%5B31m{i}</D:href>"
        "<D:status>HTTP/1.1 423 Locked</D:status></D:response>"
        for i in range(200)
    )
    body = (
        '<?xml version="1.0"?><D:multistatus xmlns:D="DAV:">'
        + members
        + "</D:multistatus>"
    )

    def script(request):
        return response(207, {"Content-Type": "application/xml"}, body.encode())

    with Wire(script) as wire:
        path = URIPath("dav" + wire.url[len("http") :] + "/d/")
        with pytest.raises(OSError) as excinfo:
            path.rm(recursive=True)
    message = str(excinfo.value)
    assert "\x1b" not in message and "\\x1b[31m" in message
    assert "and 190 more" in message and len(message) < 1500
