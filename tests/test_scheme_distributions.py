"""A scheme that another distribution provides, found through an installed
distribution's entry point in the `uripath.schemes` group: the class of the
distribution is used when it is installed, the stand-in that names what to
install when it is not, a built-in scheme cannot be taken over, and
`URIPath.schemes()` lists the name either way."""

from __future__ import annotations

import pytest

from fake_distribution import install, run
from uripath.schemes import _elsewhere

PROVIDED = ("sftp", "s3", "gs", "az")

OBJSTORE = """
    from uripath import URIPath

    class FakeObjectStorePath(URIPath):
        __SCHEMES = ("s3", "gs", "az")
        _OPTIONS = URIPath._OPTIONS | {"profile"}

        def stat(self, *, follow_symlinks=True):
            return "answered by " + type(self).__name__
"""

SFTP = """
    from uripath import URIPath

    class FakeSFTPPath(URIPath):
        __SCHEMES = ("sftp",)
"""

TAKEOVER = """
    from uripath import URIPath

    class TakesOverHTTP(URIPath):
        __SCHEMES = ("http",)

    class TakesOverFile(URIPath):
        __SCHEMES = ("file",)
"""

NEW_SCHEME = """
    from uripath import URIPath

    class FooPath(URIPath):
        __SCHEMES = ("foo",)
"""


@pytest.fixture
def sftp_distribution(tmp_path):
    return install(
        tmp_path,
        "fake-sftp",
        {"uripath.schemes": {"sftp": "fake_sftp:FakeSFTPPath"}},
        {"fake_sftp": SFTP},
    )


@pytest.fixture
def objstore_distribution(tmp_path):
    entry = "fake_objstore:FakeObjectStorePath"
    return install(
        tmp_path,
        "fake-objstore",
        {"uripath.schemes": {"s3": entry, "gs": entry, "az": entry}},
        {"fake_objstore": OBJSTORE},
    )


def test_an_installed_distribution_takes_the_scheme_it_declares(sftp_distribution):
    found = run(
        """
        import json
        from uripath import URIPath, as_path
        path = URIPath("sftp://user@host/dir/file.txt")
        child = path / "more"
        print(json.dumps([
            type(path).__name__,
            type(child).__name__,
            URIPath.scheme_class("sftp").__name__,
            URIPath.scheme_class("SFTP").__name__,
            type(URIPath("SFTP://host/x")).__name__,
            type(as_path("sftp://host/x")).__name__,
            str(child),
            type(URIPath("s3://bucket/key")).__name__,
        ]))
        """,
        sftp_distribution,
    )
    assert found == [
        "FakeSFTPPath",
        "FakeSFTPPath",
        "FakeSFTPPath",
        "FakeSFTPPath",
        "FakeSFTPPath",
        "FakeSFTPPath",
        "sftp://user@host/dir/file.txt/more",
        "ProvidedElsewhere",
    ]


def test_one_class_serves_every_scheme_a_distribution_declares_for_it(
    objstore_distribution,
):
    found = run(
        """
        import json
        from uripath import URIPath
        print(json.dumps([
            [type(URIPath(f"{s}://b/k")).__name__ for s in ("s3", "gs", "az")],
            URIPath("gs://b/k").stat(),
            type(URIPath("sftp://h/x")).__name__,
        ]))
        """,
        objstore_distribution,
    )
    assert found == [
        ["FakeObjectStorePath"] * 3,
        "answered by FakeObjectStorePath",
        "ProvidedElsewhere",
    ]


def test_the_keywords_of_the_installed_class_are_accepted_and_others_are_not(
    objstore_distribution,
):
    found = run(
        """
        import json
        from uripath import URIPath
        accepted = URIPath("s3://b/k", profile="work")
        try:
            URIPath("s3://b/k", no_such_keyword=1)
        except TypeError:
            refused = True
        print(json.dumps([type(accepted).__name__, refused]))
        """,
        objstore_distribution,
    )
    assert found == ["FakeObjectStorePath", True]


@pytest.mark.parametrize("scheme", PROVIDED)
def test_without_the_distribution_the_scheme_names_what_to_install(scheme):
    found = run(f"""
        import json
        from uripath import URIPath
        path = URIPath("{scheme}://host/dir/file.txt")
        try:
            path.stat()
        except ImportError as error:
            message = str(error)
        print(json.dumps([type(path).__name__, message]))
        """)
    assert found[0] == "ProvidedElsewhere"
    distribution = _elsewhere.SCHEMES[scheme][0]
    assert (
        f"the {scheme!r} scheme is provided by the {distribution} distribution"
        in found[1]
    )
    assert "pip install" in found[1]
    assert "host" not in found[1]


def test_the_provided_schemes_are_listed_with_and_without_the_distribution(
    sftp_distribution, objstore_distribution
):
    code = """
        import json
        from uripath import URIPath
        names = URIPath.schemes()
        print(json.dumps([[n for n in names if n in ("sftp", "s3", "gs", "az")],
                          len(names) == len(set(names))]))
        """
    expected = [["az", "gs", "s3", "sftp"], True]
    assert run(code) == expected
    assert run(code, sftp_distribution) == expected
    assert run(code, objstore_distribution) == expected


def test_a_distribution_cannot_take_over_a_built_in_scheme(tmp_path):
    install(
        tmp_path,
        "fake-takeover",
        {
            "uripath.schemes": {
                "http": "fake_takeover:TakesOverHTTP",
                "file": "fake_takeover:TakesOverFile",
            }
        },
        {"fake_takeover": TAKEOVER},
    )
    found = run(
        """
        import json, sys
        from uripath import URIPath
        names = URIPath.schemes()
        print(json.dumps([
            type(URIPath("http://h/x")).__name__,
            type(URIPath("file:///x")).__name__,
            URIPath.scheme_class("http").__name__,
            "fake_takeover" in sys.modules,
            names.count("http"),
            names.count("file"),
        ]))
        """,
        tmp_path,
    )
    assert found == ["HTTPURIPath", "FileURIPath", "HTTPURIPath", False, 1, 1]


def test_a_class_that_names_a_built_in_scheme_is_refused_when_it_is_imported(tmp_path):
    install(
        tmp_path,
        "fake-takeover",
        {"uripath.schemes": {"http": "fake_takeover:TakesOverHTTP"}},
        {"fake_takeover": TAKEOVER},
    )
    found = run(
        """
        import json
        try:
            import fake_takeover
        except ValueError as error:
            print(json.dumps(str(error)))
        """,
        tmp_path,
    )
    assert "'http' is a built-in URI scheme" in found


def test_a_distribution_can_add_a_scheme_no_one_listed(tmp_path):
    install(
        tmp_path,
        "fake-foo",
        {"uripath.schemes": {"foo": "fake_foo:FooPath"}},
        {"fake_foo": NEW_SCHEME},
    )
    code = """
        import json
        from uripath import URIPath
        print(json.dumps([type(URIPath("foo://h/x")).__name__, "foo" in URIPath.schemes()]))
        """
    assert run(code, tmp_path) == ["FooPath", True]
    assert run(code) == ["URIPath", False]
