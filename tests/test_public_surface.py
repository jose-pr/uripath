"""The public surface: what the package exports and the constructors as a type
checker reads them."""

from __future__ import annotations

import importlib
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
    "uripath": {"DerivedBackend", "Uri", "UriLike", "UriPath", "same_authority"},
    "uripath.source": {"Source", "compose_host", "compose_uri", "is_drive"},
    "uripath.query": {"Query"},
    "uripath.schemes": {
        "DataUri",
        "DavPath",
        "FileUri",
        "FtpPath",
        "GitHubPath",
        "GitLabPath",
        "GitPath",
        "HttpPath",
        "TarUri",
        "ZipUri",
    },
}


@pytest.mark.parametrize("module", sorted(DOCUMENTED))
def test_documented_names_stay_importable_from_where_they_are_documented(module):
    imported = importlib.import_module(module)
    missing = sorted(name for name in DOCUMENTED[module] if not hasattr(imported, name))
    assert missing == []


def test_the_scheme_names_of_the_package_export_every_built_in_class():
    from uripath import schemes

    assert set(schemes._EXPORTS) == DOCUMENTED["uripath.schemes"]


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
from uripath import Uri, UriPath

remote = UriPath("ftp://h/x")
allowed = UriPath("data:,x", schemesmap={})
pure = Uri("http://h/d") / "x"
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
