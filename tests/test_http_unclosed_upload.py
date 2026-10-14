"""An HTTP write stream that is garbage collected unclosed sends nothing and
warns; closing it sends the upload."""

import gc
import warnings

from http_fakes import FakeTransport, reply
from uripath import URIPath


def _path(transport):
    return URIPath("http://example.com/f.txt").with_transport(transport)


def _collect(make):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        make()
        gc.collect()
    return [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_an_unclosed_binary_upload_is_discarded_at_collection():
    transport = FakeTransport(default=reply(201))

    def make():
        stream = _path(transport).open("wb")
        stream.write(b"unfinished")
        return stream

    caught = _collect(make)
    assert transport.sent == []
    assert len(caught) == 1


def test_an_unclosed_text_upload_is_discarded_at_collection():
    transport = FakeTransport(default=reply(201))

    def make():
        stream = _path(transport).open("w", encoding="utf-8")
        stream.write("unfinished")
        return stream

    assert len(_collect(make)) >= 1
    assert transport.sent == []


def test_a_closed_upload_is_sent_once_and_collects_silently():
    transport = FakeTransport(default=reply(201))

    def make():
        stream = _path(transport).open("wb")
        stream.write(b"done")
        stream.close()
        return stream

    assert _collect(make) == []
    assert [(s.method, s.body) for s in transport.sent] == [("PUT", b"done")]
