import unittest.mock as mock
import pytest
import importlib.metadata

from uripath import URIPath


def test_plugin_dynamic_loading():
    # Verify "dummy" scheme is not registered initially
    with pytest.raises(ValueError):
        URIPath.scheme_class("dummy")

    mock_ep = mock.Mock()
    mock_ep.name = "dummy"

    def mock_load():
        class DummyPluginPath(URIPath):
            __SCHEMES = ("dummy",)

        return DummyPluginPath

    mock_ep.load.side_effect = mock_load

    def mock_entry_points(*args, **kwargs):
        if kwargs.get("group") == "uripath.schemes":
            return [mock_ep]
        return {"uripath.schemes": [mock_ep]}

    with mock.patch("importlib.metadata.entry_points", side_effect=mock_entry_points):
        # Accessing dummy:// path should trigger loading of dummy plugin
        p = URIPath("dummy://host/path")
        assert type(p).__name__ == "DummyPluginPath"
        assert type(p) is not URIPath
        assert URIPath.scheme_class("dummy") is type(p)


def test_plugin_non_matching_scheme():
    # Verify "otherdummy" scheme is not registered
    assert "otherdummy" not in URIPath.schemes()

    mock_ep = mock.Mock()
    mock_ep.name = "dummy2"

    def mock_entry_points(*args, **kwargs):
        if kwargs.get("group") == "uripath.schemes":
            return [mock_ep]
        return {"uripath.schemes": [mock_ep]}

    with mock.patch("importlib.metadata.entry_points", side_effect=mock_entry_points):
        # Accessing otherdummy:// should not load mock_ep since names don't match
        p = URIPath("otherdummy://host/path")
        assert type(p) is URIPath
        mock_ep.load.assert_not_called()


# ---------------------------------------------------------------------------
# _load_entry_point edge cases
# ---------------------------------------------------------------------------


class TestLoadEntryPoint:
    def test_returns_false_on_empty_group(self):
        with mock.patch("importlib.metadata.entry_points", return_value=[]):
            assert URIPath._load_entry_point("anything") is False

    def test_returns_false_when_no_name_match(self):
        ep = mock.Mock()
        ep.name = "other"
        with mock.patch("importlib.metadata.entry_points", return_value=[ep]):
            assert URIPath._load_entry_point("missing_xyz") is False
        ep.load.assert_not_called()

    def test_calls_load_on_match_and_returns_true(self):
        ep = mock.Mock()
        ep.name = "mytestscheme"
        ep.load.return_value = object
        with mock.patch("importlib.metadata.entry_points", return_value=[ep]):
            result = URIPath._load_entry_point("mytestscheme")
        assert result is True
        ep.load.assert_called_once()


# ---------------------------------------------------------------------------
# _load_builtin_scheme
# ---------------------------------------------------------------------------


class TestLoadBuiltinScheme:
    @pytest.mark.parametrize(
        "scheme", ["file", "data", "zip", "tar", "ftp", "ftps", "http", "https"]
    )
    def test_known_stdlib_schemes_return_true(self, scheme):
        """Schemes whose dependencies this suite always installs (stdlib,
        plus `requests` for http/https) load successfully."""
        assert URIPath._load_builtin_scheme(scheme) is True

    def test_unknown_scheme_returns_false(self):
        assert URIPath._load_builtin_scheme("__no_such_scheme_xyz__") is False

    def test_import_error_returns_false(self):
        """If the target module raises ImportError, _load_builtin_scheme returns False."""
        with mock.patch("importlib.import_module", side_effect=ImportError("no dep")):
            result = URIPath._load_builtin_scheme("ftp")
        assert result is False


# ---------------------------------------------------------------------------
# get_scheme_cls integration
# ---------------------------------------------------------------------------


class TestGetSchemeCls:
    def test_known_scheme_returns_subclass(self):
        from uripath.schemes import FileURIPath
        from uripath.source import Source

        source = Source("file", None, None, None)
        cls = source.get_scheme_cls()
        assert issubclass(cls, URIPath)

    def test_unknown_scheme_falls_back_to_uripath(self):
        from uripath.source import Source

        source = Source("__totally_unknown__", None, None, None)
        with mock.patch.object(URIPath, "_load_entry_point", return_value=False):
            with mock.patch.object(URIPath, "_load_builtin_scheme", return_value=False):
                cls = source.get_scheme_cls()
        assert cls is URIPath


def test_every_builtin_scheme_is_in_both_fallback_registries():
    """Every `__SCHEMES` value a builtin scheme class declares must resolve
    through the entry points AND `_load_builtin_scheme` -- `ftps` was
    declared by `FTPURIPath` but missing from both, so `URIPath("ftps://...")`
    returned a do-nothing `URIPath` in a fresh process. The schemes another
    distribution provides are not built in and are left out."""
    try:
        eps = importlib.metadata.entry_points(group="uripath.schemes")
    except TypeError:  # Python 3.9
        eps = importlib.metadata.entry_points().get("uripath.schemes", ())
    # The schemes package loads backends lazily: import every builtin module
    # first so the scheme map reflects all classes whose dependencies import.
    for ep in eps:
        URIPath._load_builtin_scheme(ep.name)

    from uripath.schemes import _elsewhere

    declared = {
        scheme
        for scheme in URIPath.schemes()
        if scheme not in _elsewhere.SCHEMES
        and URIPath.scheme_class(scheme).__module__.startswith("uripath.schemes")
    }
    assert "ftps" in declared
    assert sorted(declared - {ep.name for ep in eps}) == []
    assert sorted(s for s in declared if not URIPath._load_builtin_scheme(s)) == []
