"""The fenced Python blocks of README.md, docs/index.md and the extending guide
run, in document order and in one scratch directory per document, each as its
own `python -W error` process.

A block that cannot run on its own is marked by an HTML comment on the line
above its fence: `<!-- example: skip: <reason> -->` (a remote host, a method
fragment, a pytest module that another test already runs). Every block is
either run or marked, so a new example cannot be left out by accident.
"""

import os
import pathlib
import re
import shlex
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCUMENTS = ["README.md", "docs/index.md", "docs/guides/extending.md"]
SKIP = re.compile(r"^<!--\s*example:\s*skip:\s*(?P<reason>\S.*?)\s*-->$")
FENCE = re.compile(r"^```(?P<info>\S*)")


def python_blocks(text, language="python"):
    """`[(line number, source, skip reason or None)]` for every fence of
    `text` opened as ```<language>."""
    lines = text.splitlines()
    blocks = []
    index = 0
    while index < len(lines):
        fence = FENCE.match(lines[index])
        if not fence:
            index += 1
            continue
        end = index + 1
        while end < len(lines) and not lines[end].startswith("```"):
            end += 1
        if fence.group("info") == language:
            marker = SKIP.match(lines[index - 1].strip()) if index else None
            blocks.append(
                (
                    index + 1,
                    "\n".join(lines[index + 1 : end]) + "\n",
                    marker.group("reason") if marker else None,
                )
            )
        index = end + 1
    return blocks


def _cases():
    for document in DOCUMENTS:
        text = (REPO / document).read_text(encoding="utf-8")
        for line, source, reason in python_blocks(text):
            marks = [pytest.mark.skip(reason=reason)] if reason else []
            yield pytest.param(
                document, line, source, marks=marks, id=f"{document}:{line}"
            )


@pytest.fixture(scope="module")
def workdirs(tmp_path_factory):
    made = {}

    def workdir(document):
        if document not in made:
            made[document] = tmp_path_factory.mktemp(document.replace("/", "_"))
        return made[document]

    return workdir


@pytest.mark.parametrize("document, line, source", list(_cases()))
def test_the_example_runs(document, line, source, workdirs):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO / "src"), env.get("PYTHONPATH")])
    )
    result = subprocess.run(
        [sys.executable, "-W", "error", "-c", source],
        cwd=workdirs(document),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{document}:{line}\n{result.stdout}{result.stderr}"
    assert "Traceback" not in result.stderr


def test_every_document_has_python_blocks_and_each_is_run_or_marked():
    for document in DOCUMENTS:
        text = (REPO / document).read_text(encoding="utf-8")
        assert python_blocks(text), document


def test_a_marker_needs_a_reason_and_sits_directly_above_its_fence():
    blocks = python_blocks(
        "<!-- example: skip: a remote host -->\n```python\nx = 1\n```\n"
        "\n<!-- example: skip: -->\n```python\ny = 2\n```\n"
        "<!-- example: skip: far away -->\n\n```python\nz = 3\n```\n"
        "```text\nnot python\n```\n```python\nw = 4\n```\n"
    )
    assert [(line, reason) for line, _source, reason in blocks] == [
        (2, "a remote host"),
        (7, None),
        (12, None),
        (18, None),
    ]
    assert blocks[0][1] == "x = 1\n"


# --- the command lines of the README and the CLI guide run as written ---


def _command_line_blocks(document):
    text = (REPO / document).read_text(encoding="utf-8")
    if document == "README.md":
        text = text.split("\n## Command line\n", 1)[1].split("\n## ", 1)[0]
    return python_blocks(text, "bash")


def _command_line_cases():
    for document in ("README.md", "docs/guides/cli.md"):
        for line, source, reason in _command_line_blocks(document):
            marks = [pytest.mark.skip(reason=reason)] if reason else []
            yield pytest.param(document, source, marks=marks, id=f"{document}:{line}")


def test_the_command_line_section_has_commands_to_run_and_marks_the_rest():
    blocks = _command_line_blocks("README.md")
    assert [reason is None for _line, _source, reason in blocks] == [True, False]


def test_the_cli_guide_marks_only_what_cannot_run_here():
    reasons = [reason for _l, _s, reason in _command_line_blocks("docs/guides/cli.md")]
    assert reasons == ["installs the package", None, "needs an FTP host", None]


def _words_and_redirects(line):
    """The words of a command line, and the files named by `<` and `>`."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars="<>")
    lexer.whitespace_split = True
    words, stdin, stdout = [], None, None
    tokens = iter(lexer)
    for token in tokens:
        if token == "<":
            stdin = next(tokens)
        elif token == ">":
            stdout = next(tokens)
        else:
            words.append(token)
    return words, stdin, stdout


@pytest.mark.parametrize("document, source", list(_command_line_cases()))
def test_the_command_line_examples_run(document, source, tmp_path):
    """Each line is `mkdir NAME` or a `uripath` command (with `<` and `>`
    naming files), run in an empty directory with the interpreter that runs
    the tests."""
    pytest.importorskip("duho")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(REPO / "src"), env.get("PYTHONPATH")])
    )
    for line in source.splitlines():
        words, stdin, stdout = _words_and_redirects(line)
        if not words or words[0].startswith("#"):
            continue
        if words[0] == "mkdir":
            (tmp_path / words[1]).mkdir()
            continue
        assert words[0] == "uripath", line
        stdin_file = open(tmp_path / stdin, "rb") if stdin else None
        stdout_file = open(tmp_path / stdout, "wb") if stdout else subprocess.PIPE
        try:
            result = subprocess.run(
                [sys.executable, "-W", "error", "-m", "uripath"] + words[1:],
                cwd=tmp_path,
                env=env,
                stdin=stdin_file,
                stdout=stdout_file,
                stderr=subprocess.PIPE,
                timeout=120,
            )
        finally:
            for opened in (stdin_file, stdout_file):
                if opened not in (None, subprocess.PIPE):
                    opened.close()
        assert result.returncode == 0, f"{line}\n{result.stdout}{result.stderr}"
        assert b"Traceback" not in result.stderr
    if document == "README.md":
        assert (tmp_path / "site-copy" / "index.html").exists() is False
        assert (tmp_path / "site" / "copy.html").read_bytes() == b"<h1>hi</h1>"
    elif (tmp_path / "work" / "stdout.bin").exists():
        assert (tmp_path / "work" / "stdout.bin").read_bytes() == b"hello"
        assert (tmp_path / "work" / "stdin.bin").read_bytes() == b"hello"
        assert (tmp_path / "work" / "in.txt").read_bytes() == b"hello"
        assert (tmp_path / "work" / "copy.txt").read_bytes() == b"hello"
    else:
        assert (tmp_path / "work-backup").exists() is False
        assert (tmp_path / "work" / "copy.txt").read_bytes() == b"hello"
