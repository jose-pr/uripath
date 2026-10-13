"""`uripath.testing`: the transport suite that a distribution providing a
transport runs, and the files that the wheel carries for it."""

from __future__ import annotations

import ast
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import zipfile

import pytest

import uripath
from uripath import testing

TESTS = pathlib.Path(__file__).resolve().parent
REPO = TESTS.parent
PER_TRANSPORT = re.compile(
    r"\b(http_transport_kind|http_transport|on_current_transport|make_transport|"
    r"current_kind)\b"
)


try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = pytest.importorskip("tomli")


def _project():
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def _local_imports(path):
    names = {p.stem for p in TESTS.glob("*.py")}
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return {name + ".py" for name in found & names}


def test_the_modules_are_those_that_use_the_transport_fixtures():
    used = sorted(
        path.name
        for path in TESTS.glob("test_*.py")
        if path != pathlib.Path(__file__).resolve()
        and PER_TRANSPORT.search(path.read_text(encoding="utf-8"))
    )
    assert list(testing.MODULES) == used


def test_the_helpers_are_the_files_the_modules_import():
    needed = set()
    pending = [*testing.MODULES, "conftest.py"]
    while pending:
        name = pending.pop()
        for imported in _local_imports(TESTS / name) - needed:
            needed.add(imported)
            pending.append(imported)
    assert needed | {"conftest.py"} == set(testing.HELPERS)
    assert not needed & set(testing.MODULES)


def test_the_wheel_is_told_to_carry_exactly_the_suite():
    wanted = {
        f"tests/{name}": f"uripath/testing/suite/{name}"
        for name in (*testing.MODULES, *testing.HELPERS)
    }
    force = _project()["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    shipped = {k: v for k, v in force.items() if v.startswith("uripath/testing/")}
    assert shipped == wanted
    assert all((REPO / source).is_file() for source in wanted)


@pytest.mark.skipif(
    importlib.util.find_spec("hatchling") is None, reason="hatchling is not installed"
)
def test_the_built_wheel_carries_the_suite_and_the_package_around_it(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "-t",
            "wheel",
            "-d",
            str(tmp_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    (wheel,) = tmp_path.glob("uripath-*.whl")
    names = set(zipfile.ZipFile(wheel).namelist())
    for name in (*testing.MODULES, *testing.HELPERS):
        assert f"uripath/testing/suite/{name}" in names
    assert {
        "uripath/testing/__init__.py",
        "uripath/testing/__main__.py",
        "uripath/AGENTS.md",
        "uripath/py.typed",
    } <= names
    assert not any(n.startswith("uripath/testing/suite/test_p") for n in names)


def test_a_checkout_runs_the_suite_from_its_tests_directory():
    assert testing.suite_directory() == TESTS


def test_an_option_and_its_value_before_the_files_reach_the_suite_from_any_directory(
    tmp_path,
):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(pathlib.Path(uripath.__file__).resolve().parent.parent),
                env.get("PYTHONPATH"),
            ],
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uripath.testing",
            "--http-transports",
            "builtin",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_http_transport.py::" in result.stdout


def test_the_suite_is_listed_by_the_command_and_runs_once_per_transport():
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [
                str(pathlib.Path(uripath.__file__).resolve().parent.parent),
                env.get("PYTHONPATH"),
            ],
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uripath.testing",
            "--http-transports",
            "builtin",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=REPO,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    listed = result.stdout.splitlines()
    assert any(
        "test_http_transport.py::" in line and line.endswith("[builtin]")
        for line in listed
    )
    assert not any("test_http_pool.py" in line for line in listed)
