"""The command line beside the library: the extra it needs, what importing the
package loads, and the command line served as tools and described to agents."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import uripath

_SRC = str(Path(uripath.__file__).resolve().parent.parent)

#: Blocks duho the way a missing extra does. `find_spec`, not the legacy
#: `find_module`: that hook was removed in 3.12, so a finder defining only it
#: is ignored and the import quietly succeeds.
_BLOCK_DUHO = (
    "import sys, importlib.abc\n"
    "class B(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'duho' or name.startswith('duho.'):\n"
    "            raise ModuleNotFoundError('blocked', name='duho')\n"
    "        return None\n"
    "sys.meta_path.insert(0, B())\n"
)


def _child(code, *argv, env=None):
    base = dict(os.environ)
    base["PYTHONPATH"] = os.pathsep.join(
        [_SRC] + ([base["PYTHONPATH"]] if base.get("PYTHONPATH") else [])
    )
    base.update(env or {})
    return subprocess.run(
        [sys.executable, "-W", "error", "-c", code, *argv],
        capture_output=True,
        text=True,
        env=base,
        timeout=120,
    )


def test_importing_the_package_loads_neither_the_command_line_nor_duho():
    result = _child(
        "import sys, uripath\n"
        "loaded = sorted(m for m in sys.modules if m == 'duho' or "
        "m.startswith(('duho.', 'uripath.cli')))\n"
        "assert not loaded, loaded\n"
        "assert 'cli' not in uripath.__all__\n"
    )
    assert result.returncode == 0, result.stderr


def test_the_script_without_the_extra_names_it_and_exits_non_zero():
    result = _child(
        _BLOCK_DUHO + "from uripath.cli import main\n"
        "raise SystemExit(main(['read', 'x']))\n"
    )
    assert result.returncode == 1
    assert 'pip install "pathapi-uri[cli]"' in result.stderr
    assert (
        "Traceback" not in result.stderr and "ModuleNotFoundError" not in result.stderr
    )
    assert result.stdout == ""


def test_python_dash_m_without_the_extra_names_it_and_exits_non_zero():
    result = _child(
        _BLOCK_DUHO + "import runpy\n"
        "runpy.run_module('uripath', run_name='__main__')\n"
    )
    assert result.returncode == 1
    assert 'pip install "pathapi-uri[cli]"' in result.stderr
    assert "Traceback" not in result.stderr


def test_a_failure_inside_duho_is_not_taken_for_a_missing_extra():
    result = _child(
        "import sys, importlib.abc\n"
        "class B(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'duho':\n"
        "            raise ModuleNotFoundError('broken inside duho', name='something_else')\n"
        "sys.meta_path.insert(0, B())\n"
        "from uripath.cli import main\n"
        "main(['read', 'x'])\n"
    )
    assert result.returncode != 0
    assert "broken inside duho" in result.stderr
    assert "pip install" not in result.stderr


def test_the_root_command_is_found_on_first_use():
    pytest.importorskip("duho")
    from uripath import cli
    from uripath.cli._root import Uripath

    assert cli.Uripath is Uripath
    with pytest.raises(AttributeError):
        cli.Nothing


def test_python_dash_m_runs_the_command_line():
    pytest.importorskip("duho")
    result = _child(
        "import runpy, sys\n"
        "sys.argv = ['uripath', '--version']\n"
        "runpy.run_module('uripath', run_name='__main__')\n"
    )
    assert result.returncode == 0, result.stderr
    assert uripath.__version__ in result.stdout


# --- served as tools, described to agents ---

duho = pytest.importorskip("duho")
from duho.mcp import call_tool, describe_tools  # noqa: E402

from uripath.cli._root import Uripath  # noqa: E402

_COMMANDS = ["read", "write", "rm", "cp", "sync"]


def _tools():
    return {tool["name"]: tool for tool in describe_tools(Uripath)}


def _text(result):
    return " ".join(item["text"] for item in result["content"])


def test_every_command_is_a_tool():
    assert list(_tools()) == [f"uripath.{name}" for name in _COMMANDS]


def test_every_field_says_what_it_is_and_what_omitting_it_means():
    for name, tool in _tools().items():
        for field, schema in tool["inputSchema"]["properties"].items():
            assert schema.get("description"), f"{name}: {field}"


def test_the_fields_that_destroy_or_replace_are_off_unless_given():
    tools = _tools()
    properties = {
        name: tool["inputSchema"]["properties"] for name, tool in tools.items()
    }
    assert properties["uripath.rm"]["recursive"]["default"] is False
    assert properties["uripath.sync"]["remove_missing"]["default"] is False
    assert properties["uripath.sync"]["dry_run"]["default"] is False
    assert properties["uripath.cp"]["overwrite"]["default"] is False
    assert "path" in tools["uripath.rm"]["inputSchema"]["required"]


def test_no_default_carries_a_value_a_user_could_have_to_hide():
    allowed = (None, [], {}, 0, True, False, "utf-8")
    for name, tool in _tools().items():
        for field, schema in tool["inputSchema"]["properties"].items():
            if "default" in schema:
                assert schema["default"] in allowed, f"{name}: {field}"


def test_a_tool_call_reads_a_file(tmp_path):
    (tmp_path / "f.txt").write_bytes(b"hello")
    result = call_tool(Uripath, "uripath.read", {"path": str(tmp_path / "f.txt")})
    assert not result.get("isError")
    assert _text(result) == "hello"


def test_a_tool_cannot_read_the_standard_input_the_server_listens_on():
    result = call_tool(Uripath, "uripath.read", {"path": "-"})
    assert result["isError"]
    assert "standard input is not available" in _text(result)


def test_a_tool_cannot_write_from_the_standard_input_either(tmp_path):
    result = call_tool(Uripath, "uripath.write", {"path": str(tmp_path / "w.txt")})
    assert result["isError"]
    assert not (tmp_path / "w.txt").exists()


def test_a_tool_call_removes_a_tree_only_when_it_says_recursive(tmp_path):
    (tmp_path / "d" / "sub").mkdir(parents=True)
    (tmp_path / "d" / "sub" / "y").write_text("x", encoding="utf-8")
    refused = call_tool(Uripath, "uripath.rm", {"path": str(tmp_path / "d")})
    assert refused["isError"]
    assert (tmp_path / "d" / "sub" / "y").exists()
    done = call_tool(
        Uripath, "uripath.rm", {"path": str(tmp_path / "d"), "recursive": True}
    )
    assert not done.get("isError")
    assert not (tmp_path / "d").exists()


def test_a_tool_call_deletes_from_the_target_only_when_it_says_remove_missing(
    tmp_path,
):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (target / "extra.txt").write_text("extra", encoding="utf-8")
    arguments = {"source": str(source), "target": str(target)}
    assert not call_tool(Uripath, "uripath.sync", arguments).get("isError")
    assert (target / "extra.txt").exists()
    assert not call_tool(
        Uripath, "uripath.sync", {**arguments, "remove_missing": True}
    ).get("isError")
    assert not (target / "extra.txt").exists()


def test_a_tool_call_that_fails_says_so_and_names_the_error(tmp_path):
    result = call_tool(Uripath, "uripath.read", {"path": str(tmp_path / "nope")})
    assert result["isError"]
    assert "FileNotFoundError" in _text(result)


def test_agent_help_describes_the_whole_tree(capsys, monkeypatch):
    from uripath.cli import main

    monkeypatch.setenv("AGENT_HELP", "1")
    assert main(["--help"]) == 0
    document = json.loads(capsys.readouterr().out)
    text = json.dumps(document)
    for name in _COMMANDS:
        assert f'"{name}"' in text
    assert "130" in text and "141" not in text
