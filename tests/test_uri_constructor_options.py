"""A constructor accepts the keyword arguments its class names and raises
`TypeError` for any other: a misspelt `backend=` must not mean "use the
default"."""

from __future__ import annotations

import pickle

import pytest

from uripath import URI, URIPath
from uripath.schemes import (
    ArchiveURIPath,
    DAVURIPath,
    DataURIPath,
    FileURIPath,
    FTPURIPath,
    HTTPURIPath,
    ZipURIPath,
)

MISSPELT = object()

URIS = {
    "uri": lambda **kw: URI("x/y", **kw),
    "bare-class": lambda **kw: URIPath("x/y", **kw),
    "http": lambda **kw: URIPath("http://h/x", **kw),
    "http-class": lambda **kw: HTTPURIPath("http://h/x", **kw),
    "dav": lambda **kw: DAVURIPath("dav://h/x", **kw),
    "file": lambda **kw: FileURIPath("file:///x", **kw),
    "data": lambda **kw: DataURIPath("data:,x", **kw),
    "ftp": lambda **kw: FTPURIPath("ftp://h/x", **kw),
    "zip": lambda **kw: ZipURIPath("zip:file:///a.zip!/x", **kw),
    "archive": lambda **kw: ArchiveURIPath("archive:file:///a.zip!/x", **kw),
}


@pytest.mark.parametrize("name", URIS)
def test_an_unknown_keyword_argument_is_a_type_error_naming_it(name):
    with pytest.raises(TypeError, match="backnd"):
        URIS[name](backnd=MISSPELT)


# The backend of an archive path is the open archive, not a free-form object.
HAS_FREE_BACKEND = [n for n in URIS if n not in ("uri", "zip", "archive")]


@pytest.mark.parametrize("name", HAS_FREE_BACKEND)
def test_backend_is_accepted_by_every_path_class(name):
    backend = object()
    path = URIS[name](backend=backend)
    assert path.backend is backend


def test_a_plain_uri_takes_no_keyword_argument():
    with pytest.raises(TypeError, match="anything"):
        URI("x", anything=1)
    with pytest.raises(TypeError, match="backend"):
        URI("x", backend=object())


def test_the_options_of_the_dispatching_constructor_are_accepted():
    path = URIPath("http://h/x", schemesmap={"http": HTTPURIPath}, findclass=True)
    assert isinstance(path, HTTPURIPath)


def test_a_keyword_for_another_scheme_is_refused_after_dispatch():
    with pytest.raises(TypeError, match="ssh_config"):
        URIPath("http://h/x", ssh_config="~/.ssh/config")


class OptionedPath(URIPath):
    """A scheme that reads a keyword of its own."""

    __SCHEMES = ("optg5",)
    __slots__ = ()
    _OPTIONS = URIPath._OPTIONS | {"flavor"}


def test_a_scheme_names_its_own_keyword_arguments():
    path = URIPath("optg5://h/x", flavor="mild")
    assert isinstance(path, OptionedPath)
    assert OptionedPath("optg5://h/x", flavor="mild", backend=None).path == "/x"
    with pytest.raises(TypeError, match="flavour"):
        URIPath("optg5://h/x", flavour="mild")
    with pytest.raises(TypeError, match="flavor"):
        URIPath("http://h/x", flavor="mild")


@pytest.mark.parametrize("scheme", ["sftp", "s3", "gs", "az"])
def test_a_scheme_another_distribution_provides_takes_any_keyword(scheme):
    # Its keywords are the other distribution's to name: the path is built
    # with them and the first operation that needs the server says what to
    # install.
    path = URIPath(f"{scheme}://h/x", ssh_config="~/.ssh/config", client_kwargs={})
    with pytest.raises(ImportError, match="pip install"):
        path.stat()


def test_a_derived_path_and_a_pickle_pass_no_keyword_the_class_lacks():
    path = URIPath("http://h/a?x=1")
    assert (path / "b").as_uri() == "http://h/a/b?x=1"
    assert path.with_backend(object()).as_uri() == "http://h/a?x=1"
    assert pickle.loads(pickle.dumps(path)).as_uri() == "http://h/a?x=1"
