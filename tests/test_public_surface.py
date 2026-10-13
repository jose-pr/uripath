"""The public surface: what the package exports and the constructors as a type
checker reads them."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import uripath

PACKAGE = pathlib.Path(uripath.__file__).resolve().parent
HEADER = PACKAGE / "AGENTS.md"

# The names the shipped header documents, by the module they are imported from.
DOCUMENTED = {
    "uripath": {
        "__version__",
        "as_path",
        "copy_stream",
        "Query",
        "QueryLike",
        "Source",
        "URI",
        "URILike",
        "URIPath",
        "URIPathError",
        "URISyntaxError",
        "UnsupportedSchemeError",
    },
    "uripath.exceptions": {
        "InsecureTransportWarning",
        "OutputClosedError",
        "URIPathError",
        "URISyntaxError",
        "UnsupportedSchemeError",
    },
    "uripath.source": {
        "ERRORS",
        "SAFE_PATH",
        "Source",
        "compose_host",
        "compose_uri",
        "fold_host",
        "is_drive",
        "percent_encode",
        "same_authority",
    },
    "uripath.query": {"Query", "QueryLike"},
    "uripath.cli": {"main"},
    "uripath.schemes": {
        "ArchiveTarURIPath",
        "ArchiveURIPath",
        "ArchiveZipURIPath",
        "BaseFTPURIBackend",
        "BaseRepoBackend",
        "DAVURIPath",
        "DataURIPath",
        "DerivedBackend",
        "FTPURIBackend",
        "FTPURIPath",
        "FileURIPath",
        "GitHubGitURIPath",
        "GitHubURIPath",
        "GitLabGitURIPath",
        "GitLabURIPath",
        "GitURIPath",
        "HTTPAppendStream",
        "HTTPBackend",
        "HTTPResponse",
        "HTTPTransport",
        "HTTPURIPath",
        "HTTPWriteStream",
        "MAX_LISTING_BYTES",
        "MEMBER_SPOOL_BYTES",
        "RepoBackend",
        "TarURIPath",
        "ZipURIPath",
    },
}


@pytest.mark.parametrize("module", sorted(DOCUMENTED))
def test_documented_names_stay_importable_from_where_they_are_documented(module):
    imported = importlib.import_module(module)
    missing = sorted(name for name in DOCUMENTED[module] if not hasattr(imported, name))
    assert missing == []


def test_the_package_exports_exactly_the_documented_names():
    from uripath import schemes

    assert set(schemes.__all__) == DOCUMENTED["uripath.schemes"]
    assert set(schemes._EXPORTS) <= set(schemes.__all__)
    for name in schemes.__all__:
        assert hasattr(schemes, name), name


def test_every_public_module_declares_all_and_the_others_are_private():
    import pkgutil

    public = sorted(
        info.name
        for info in pkgutil.walk_packages(uripath.__path__, "uripath.")
        if not any(part.startswith("_") for part in info.name.split(".")[1:])
    )
    assert public == [
        "uripath.cli",
        "uripath.cli.cp",
        "uripath.cli.read",
        "uripath.cli.rm",
        "uripath.cli.sync",
        "uripath.cli.write",
        "uripath.exceptions",
        "uripath.query",
        "uripath.schemes",
        "uripath.source",
    ]
    has_duho = importlib.util.find_spec("duho") is not None
    for name in ["uripath", *public]:
        if name.startswith("uripath.cli.") and not has_duho:
            continue
        module = importlib.import_module(name)
        assert isinstance(module.__all__, (list, tuple)), name
        assert all(hasattr(module, member) for member in module.__all__), name


@pytest.mark.parametrize("module", sorted(DOCUMENTED))
def test_a_public_module_exports_exactly_the_documented_names(module):
    assert set(importlib.import_module(module).__all__) == DOCUMENTED[module]


def _header_import_lines():
    text = HEADER.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)
    for block in blocks:
        for line in block.splitlines():
            if re.match(r"(from \S+ import |import )", line):
                yield line


def test_the_import_lines_of_the_header_run():
    lines = list(_header_import_lines())
    for line in lines:
        exec(line, {})


CONSUMER = """\
from uripath import URI, URIPath

remote = URIPath("ftp://h/x")
allowed = URIPath("data:,x", schemesmap={})
pure = URI("http://h/d") / "x"
"""


def _consumer(tmp_path):
    # Outside any dot-directory: pyright silently skips those.
    directory = tmp_path / "consumer"
    directory.mkdir()
    (directory / "consumer.py").write_text(CONSUMER, encoding="utf-8")
    return directory


def test_mypy_accepts_the_constructors(tmp_path, monkeypatch):
    api = pytest.importorskip("mypy.api")
    directory = _consumer(tmp_path)
    monkeypatch.setenv("MYPYPATH", str(PACKAGE.parent))
    out, err, status = api.run(
        [
            "--follow-imports=silent",
            "--no-incremental",
            "--cache-dir=" + str(tmp_path / "mypy-cache"),
            str(directory / "consumer.py"),
        ]
    )
    assert status == 0, out + err


@pytest.mark.allow_program("pyright", "basedpyright")
def test_pyright_accepts_the_constructors(tmp_path):
    checker = shutil.which("pyright") or shutil.which("basedpyright")
    if checker is None:
        pytest.skip("pyright is not installed")
    directory = _consumer(tmp_path)
    (directory / "pyrightconfig.json").write_text(
        json.dumps(
            {"typeCheckingMode": "standard", "extraPaths": [str(PACKAGE.parent)]}
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [checker, "--pythonpath", sys.executable, "consumer.py"],
        capture_output=True,
        text=True,
        cwd=directory,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_module_postpones_the_evaluation_of_annotations():
    # A bare `X | Y` in an annotation must not be evaluated on Python 3.9.
    without = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if "from __future__ import annotations" not in path.read_text(encoding="utf-8")
    )
    assert without == []
