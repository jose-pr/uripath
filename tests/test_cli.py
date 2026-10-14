"""The `uripath` command line, driven through the real parser.

A command is built from an argument vector with `duho.parse` and called, or run
whole through `main`, so the fields, the flags and the exit status are the ones
a user gets. The standard streams are replaced by objects that carry a binary
`.buffer`, which is where the commands read and write bytes.
"""

from __future__ import annotations

import errno
import io
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

duho = pytest.importorskip("duho")

import uripath  # noqa: E402
from pathlib_next import LocalPath  # noqa: E402
from uripath.cli import main  # noqa: E402
from uripath.cli import sync as sync_module  # noqa: E402
from uripath.cli._root import Uripath  # noqa: E402

_MEBIBYTE = 1024 * 1024


class _Std:
    """A standard stream of the process: bytes through `.buffer`; the text
    layer keeps what is written to it in `text`."""

    def __init__(self, buffer):
        self.buffer = buffer
        self.text = []

    def write(self, data):
        self.text.append(data)
        return len(data)

    def flush(self):
        pass

    def isatty(self):
        return False


@pytest.fixture(autouse=True)
def _logging_is_left_as_found():
    logger = logging.getLogger("uripath")
    level = logger.level
    yield
    logger.setLevel(level)


@pytest.fixture
def run(monkeypatch, capsys):
    """`run(*argv, stdin=b"", stdout=None)`: `main(argv)` with those streams;
    returns `(status, stdout bytes, stderr text)`."""

    def run(*argv, stdin=b"", stdout=None):
        out = io.BytesIO() if stdout is None else stdout
        reader = stdin if hasattr(stdin, "read") else io.BytesIO(stdin)
        monkeypatch.setattr(sys, "stdin", _Std(reader))
        monkeypatch.setattr(sys, "stdout", _Std(out))
        status = main(list(argv))
        err = capsys.readouterr().err
        return status, out.getvalue() if isinstance(out, io.BytesIO) else b"", err

    return run


def _command(*argv):
    """The command the real parser builds from `argv`."""
    return duho.parse(Uripath, list(argv))


@pytest.fixture
def stdio(monkeypatch):
    """`stdio(stdin=b"", stdout=None)` replaces the streams and returns the
    binary stdout, for a test that calls a command it built itself."""

    def stdio(stdin=b"", stdout=None):
        out = io.BytesIO() if stdout is None else stdout
        reader = stdin if hasattr(stdin, "read") else io.BytesIO(stdin)
        monkeypatch.setattr(sys, "stdin", _Std(reader))
        monkeypatch.setattr(sys, "stdout", _Std(out))
        return out

    return stdio


def test_help_lists_the_commands(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in ("read", "write", "rm", "cp", "sync"):
        assert name in out


def test_help_of_a_command_returns_zero_instead_of_exiting(capsys):
    assert main(["read", "--help"]) == 0
    assert "file or URI to read" in capsys.readouterr().out


def test_version_is_the_distribution_s(capsys):
    assert main(["--version"]) == 0
    assert uripath.__version__ in capsys.readouterr().out


def test_read_local_file_to_stdout(run, tmp_path):
    path = tmp_path / "input.txt"
    path.write_bytes(b"hello")
    status, out, err = run("read", str(path))
    assert (status, out, err) == (0, b"hello", "")


def test_read_a_command_built_from_the_vector_and_called(stdio, tmp_path):
    path = tmp_path / "input.txt"
    path.write_bytes(b"hello")
    out = stdio()
    assert _command("read", str(path))() == 0
    assert out.getvalue() == b"hello"


def test_read_dash_copies_stdin_to_stdout(run):
    status, out, _ = run("read", "-", stdin=b"pipe")
    assert (status, out) == (0, b"pipe")


def test_write_stdin_to_local_file(run, tmp_path):
    path = tmp_path / "output.txt"
    assert run("write", str(path), stdin=b"data")[0] == 0
    assert path.read_bytes() == b"data"


def test_write_argument_to_local_file(run, tmp_path):
    path = tmp_path / "output.txt"
    assert run("write", str(path), "text")[0] == 0
    assert path.read_text(encoding="utf-8") == "text"


def test_write_encodes_the_argument_with_the_encoding_given(run, tmp_path):
    path = tmp_path / "output.txt"
    assert run("write", str(path), "café", "--encoding", "latin-1")[0] == 0
    assert path.read_bytes() == b"caf\xe9"


def test_write_to_dash_writes_the_argument_to_stdout(run):
    status, out, _ = run("write", "-", "data")
    assert (status, out) == (0, b"data")


def test_write_still_overwrites_by_design(run, tmp_path):
    target = tmp_path / "w.txt"
    target.write_bytes(b"old")
    assert run("write", str(target), "new")[0] == 0
    assert target.read_bytes() == b"new"


def test_cp_local_file_to_local_file(run, tmp_path):
    source, target = tmp_path / "source.txt", tmp_path / "target.txt"
    source.write_bytes(b"copy")
    assert run("cp", str(source), str(target))[0] == 0
    assert target.read_bytes() == b"copy"


def test_cp_refuses_an_existing_target_without_overwrite(run, tmp_path):
    source, target = tmp_path / "source.txt", tmp_path / "target.txt"
    source.write_bytes(b"new")
    target.write_bytes(b"old")
    status, _, err = run("cp", str(source), str(target))
    assert status == 1 and "FileExistsError" in err
    assert target.read_bytes() == b"old"
    assert run("cp", "--overwrite", str(source), str(target))[0] == 0
    assert target.read_bytes() == b"new"


def test_cp_recursive_copies_a_tree(run, tmp_path):
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "src" / "sub" / "f.txt").write_text("x", encoding="utf-8")
    assert run("cp", "-r", str(tmp_path / "src"), str(tmp_path / "dst"))[0] == 0
    assert (tmp_path / "dst" / "sub" / "f.txt").read_text(encoding="utf-8") == "x"


def test_cp_stdin_to_local_file(run, tmp_path):
    target = tmp_path / "target.txt"
    assert run("cp", "-", str(target), stdin=b"copy")[0] == 0
    assert target.read_bytes() == b"copy"


def test_cp_local_file_to_stdout(run, tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"copy")
    status, out, _ = run("cp", str(source), "-")
    assert (status, out) == (0, b"copy")


def test_rm_removes_a_file_and_refuses_a_directory_with_content(run, tmp_path):
    (tmp_path / "root" / "child").mkdir(parents=True)
    (tmp_path / "root" / "child" / "file.txt").write_text("x", encoding="utf-8")
    (tmp_path / "gone.txt").write_text("x", encoding="utf-8")
    assert run("rm", str(tmp_path / "gone.txt"))[0] == 0
    assert not (tmp_path / "gone.txt").exists()
    assert run("rm", str(tmp_path / "root"))[0] == 1
    assert (tmp_path / "root" / "child" / "file.txt").exists()


def test_rm_recursive(run, tmp_path):
    root = tmp_path / "root"
    (root / "child").mkdir(parents=True)
    (root / "child" / "file.txt").write_text("x", encoding="utf-8")
    assert run("rm", "--recursive", str(root))[0] == 0
    assert not root.exists()


def test_rm_of_a_missing_path_fails_unless_told_to_accept_it(run, tmp_path):
    missing = tmp_path / "missing"
    status, _, err = run("rm", str(missing))
    assert status == 1 and "FileNotFoundError" in err
    assert run("rm", "--missing-ok", str(missing))[0] == 0


def test_sync_remove_missing(run, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "keep.txt").write_text("keep", encoding="utf-8")
    (target / "extra.txt").write_text("extra", encoding="utf-8")
    assert run("sync", "--remove-missing", str(source), str(target))[0] == 0
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (target / "extra.txt").exists()


def test_sync_keeps_what_the_source_lacks_unless_told_to_remove_it(run, tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (target / "extra.txt").write_text("extra", encoding="utf-8")
    assert run("sync", str(source), str(target))[0] == 0
    assert (target / "extra.txt").read_text(encoding="utf-8") == "extra"


def test_an_error_returns_one_and_writes_one_line_to_stderr(run, tmp_path):
    status, out, err = run("read", str(tmp_path / "missing.txt"))
    assert status == 1 and out == b""
    assert err.startswith("uripath: FileNotFoundError: ")
    assert err.count("\n") == 1


def _sync_trees(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "version.txt").write_text("0.9.3", encoding="utf-8")
    (target / "version.txt").write_text("0.9.2", encoding="utf-8")
    return source, target


def test_sync_copies_a_same_size_edit(run, tmp_path):
    source, target = _sync_trees(tmp_path)
    assert run("sync", str(source), str(target))[0] == 0
    assert (target / "version.txt").read_text(encoding="utf-8") == "0.9.3"


def test_sync_size_only_keeps_the_size_comparison(run, tmp_path):
    source, target = _sync_trees(tmp_path)
    assert run("sync", "--size-only", str(source), str(target))[0] == 0
    assert (target / "version.txt").read_text(encoding="utf-8") == "0.9.2"


def _mount_named_mounted(monkeypatch):
    # A mount point needs privileges to create: `is_mount()` says so for a
    # directory called `mounted`.
    real = LocalPath.is_mount
    monkeypatch.setattr(
        LocalPath, "is_mount", lambda self: self.name == "mounted" or real(self)
    )


def _mount_trees(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    (source / "mounted").mkdir(parents=True)
    (source / "mounted" / "new.txt").write_text("new", encoding="utf-8")
    (target / "mounted").mkdir(parents=True)
    (target / "mounted" / "theirs.txt").write_text("theirs", encoding="utf-8")
    return source, target


def test_sync_goes_into_a_mount_point_unless_told_not_to(run, tmp_path, monkeypatch):
    _mount_named_mounted(monkeypatch)
    source, target = _mount_trees(tmp_path)
    assert run("sync", str(source), str(target))[0] == 0
    assert (target / "mounted" / "new.txt").read_text(encoding="utf-8") == "new"


def test_sync_no_follow_mounts_fails_on_a_mount_point_and_leaves_it(
    run, tmp_path, monkeypatch
):
    _mount_named_mounted(monkeypatch)
    source, target = _mount_trees(tmp_path)
    status, _, err = run("sync", "--no-follow-mounts", str(source), str(target))
    assert status == 1
    assert "mounted" in err
    assert [p.name for p in (target / "mounted").iterdir()] == ["theirs.txt"]


def test_sync_dry_run_prints_planned_changes_and_changes_nothing(run, tmp_path):
    source, target = _sync_trees(tmp_path)
    (source / "new.txt").write_text("new", encoding="utf-8")
    (target / "stale.txt").write_text("stale", encoding="utf-8")
    status, out, _ = run(
        "sync", "--dry-run", "--remove-missing", str(source), str(target)
    )
    assert status == 0
    lines = out.decode("utf-8").splitlines()
    assert f"would copy {source / 'new.txt'} -> {target / 'new.txt'}" in lines
    assert f"would copy {source / 'version.txt'} -> {target / 'version.txt'}" in lines
    assert any(line.startswith("would remove ") for line in lines)
    assert not (target / "new.txt").exists()
    assert (target / "stale.txt").exists()
    assert (target / "version.txt").read_text(encoding="utf-8") == "0.9.2"


def test_sync_is_quiet_by_default_and_lists_the_changes_it_makes_under_v(run, tmp_path):
    source, target = _sync_trees(tmp_path)
    assert run("sync", str(source), str(target)) == (0, b"", "")
    (source / "version.txt").write_text("1.0.0", encoding="utf-8")
    status, out, _ = run("sync", "-v", str(source), str(target))
    expected = f"copy {source / 'version.txt'} -> {target / 'version.txt'}"
    assert (status, out.decode("utf-8").splitlines()) == (0, [expected])


def test_sync_quiet_flag_cancels_verbose(run, tmp_path):
    source, target = _sync_trees(tmp_path)
    status, out, _ = run("sync", "-v", "-q", str(source), str(target))
    assert (status, out) == (0, b"")
    assert (target / "version.txt").read_text(encoding="utf-8") == "0.9.3"


def test_sync_dry_run_fails_for_a_link_the_target_cannot_hold_like_the_real_run(
    tmp_path, monkeypatch, run
):
    from pathlib_next.mempath import MemPath

    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("aaa", encoding="utf-8")
    try:
        (source / "lnk").symlink_to("a.txt")
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlink unavailable: {error}")
    target = MemPath("/target")
    target.mkdir()
    real = sync_module.as_path
    monkeypatch.setattr(
        sync_module, "as_path", lambda text: target if text == "memory" else real(text)
    )

    results = {}
    for flag in ("--dry-run", "-v"):
        status, out, err = run(
            "sync", flag, "--no-follow-symlinks", str(source), "memory"
        )
        lines = out.decode("utf-8").splitlines()
        assert not [x for x in lines if x.startswith(("would symlink", "symlink"))]
        results[flag] = (status, err)

    assert results["--dry-run"] == results["-v"]
    status, message = results["--dry-run"]
    assert status == 1
    assert "NotImplementedError" in message and "MemPath" in message


class _RecordingWriter(io.BytesIO):
    def __init__(self):
        super().__init__()
        self.sizes = []

    def write(self, data):
        self.sizes.append(len(data))
        return super().write(data)


class _RecordingReader(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.sizes = []

    def read(self, size=-1):
        self.sizes.append(size)
        return super().read(size)


_BIG = bytes(range(256)) * (3 * _MEBIBYTE // 256 + 1)


def test_read_streams_in_chunks(run, tmp_path):
    path = tmp_path / "big.bin"
    path.write_bytes(_BIG)
    stdout = _RecordingWriter()
    assert run("read", str(path), stdout=stdout)[0] == 0
    assert stdout.getvalue() == _BIG
    assert len(stdout.sizes) > 1
    assert max(stdout.sizes) <= _MEBIBYTE


def test_cp_dash_streams_in_chunks(run, tmp_path):
    target = tmp_path / "target.bin"
    stdin = _RecordingReader(_BIG)
    assert run("cp", "-", str(target), stdin=stdin)[0] == 0
    assert target.read_bytes() == _BIG
    assert stdin.sizes and all(0 < size <= _MEBIBYTE for size in stdin.sizes)

    stdout = _RecordingWriter()
    assert run("cp", str(target), "-", stdout=stdout)[0] == 0
    assert stdout.getvalue() == _BIG
    assert max(stdout.sizes) <= _MEBIBYTE

    stdin, stdout = _RecordingReader(b"piped"), _RecordingWriter()
    assert run("read", "-", stdin=stdin, stdout=stdout)[0] == 0
    assert stdout.getvalue() == b"piped"
    assert all(0 < size <= _MEBIBYTE for size in stdin.sizes)


def test_cp_stdin_refuses_an_existing_target_without_overwrite(run, tmp_path):
    target = tmp_path / "important.bin"
    target.write_bytes(b"precious")
    status, _, err = run("cp", "-", str(target), stdin=b"clobbered")
    assert status == 1
    assert "FileExistsError" in err
    assert target.read_bytes() == b"precious"


def test_cp_stdin_overwrites_with_overwrite(run, tmp_path):
    target = tmp_path / "important.bin"
    target.write_bytes(b"precious")
    assert run("cp", "--overwrite", "-", str(target), stdin=b"replaced")[0] == 0
    assert target.read_bytes() == b"replaced"


@pytest.mark.parametrize("argv", [["cp", "-r", "-", "t.bin"], ["cp", "-r", "x", "-"]])
def test_cp_recursive_with_dash_is_a_wrong_invocation(argv, run, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    status, out, err = run(*argv, stdin=b"x")
    assert (status, out) == (2, b"")
    assert "--recursive" in err
    assert list(tmp_path.iterdir()) == []


def test_write_to_a_colon_name_writes_a_local_file(run, tmp_path, monkeypatch):
    # "12:30.txt" is not a valid Windows file name; the rule that keeps it
    # local is tested for every platform with `as_path`.
    if sys.platform == "win32":
        pytest.skip("':' is not allowed in Windows file names")
    monkeypatch.chdir(tmp_path)
    assert run("write", "12:30.txt", "hi")[0] == 0
    assert (tmp_path / "12:30.txt").read_bytes() == b"hi"


def test_a_scheme_another_distribution_provides_names_it(run):
    status, _, err = run("read", "sftp://h/x")
    assert status == 1
    assert "ImportError" in err and "sftppath" in err


class _ClosedPipe(io.BytesIO):
    def write(self, data):
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(32, "Broken pipe")


def test_read_into_a_closed_pipe_exits_quietly_with_the_sigpipe_status(run, tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(b"x" * (3 * _MEBIBYTE))
    status, _, err = run("read", str(source), stdout=_ClosedPipe())
    assert (status, err) == (141, "")


def test_write_argument_to_a_closed_pipe_exits_quietly(run):
    assert run("write", "-", "data", stdout=_ClosedPipe()) == (141, b"", "")


def test_a_broken_pipe_from_a_source_is_still_reported(run, monkeypatch, tmp_path):
    # Only stdout going away is quiet: a connection that breaks mid-copy is
    # an error.
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr(LocalPath, "open", lambda self, *a, **k: Broken())
    status, _, err = run("read", str(tmp_path / "x"))
    assert status == 1
    assert "BrokenPipeError" in err


def test_keyboard_interrupt_exits_130_without_a_traceback(run, monkeypatch):
    def interrupted(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(sys.modules["uripath.cli.cp"].Cp, "__call__", interrupted)
    status, _, err = run("cp", "a", "b")
    assert (status, err) == (130, "")


class _InvalidArgumentPipe(io.BytesIO):
    """The stdout of Windows after the reader closed: EINVAL, not EPIPE."""

    def write(self, data):
        raise OSError(errno.EINVAL, "Invalid argument")

    def flush(self):
        raise OSError(errno.EINVAL, "Invalid argument")


def test_einval_from_stdout_is_a_closed_pipe_on_windows(run, monkeypatch):
    monkeypatch.setattr(sys.modules["uripath._transfer"], "_WINDOWS", True)
    assert run("write", "-", "data", stdout=_InvalidArgumentPipe()) == (141, b"", "")


def test_einval_from_stdout_is_an_error_elsewhere(run, monkeypatch):
    monkeypatch.setattr(sys.modules["uripath._transfer"], "_WINDOWS", False)
    status, _, err = run("write", "-", "data", stdout=_InvalidArgumentPipe())
    assert status == 1
    assert err.startswith("uripath: OSError:")


_SRC = str(Path(uripath.__file__).resolve().parent.parent)


def _child_env():
    """The environment of a child interpreter that imports this checkout."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [_SRC] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return env


def test_a_real_pipe_closed_by_the_reader_exits_quietly(tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(b"y" * (8 * _MEBIBYTE))
    proc = subprocess.Popen(
        [sys.executable, "-m", "uripath", "read", str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_child_env(),
    )
    assert proc.stdout.read(10) == b"y" * 10
    proc.stdout.close()
    err = proc.stderr.read()
    proc.stderr.close()
    assert proc.wait(timeout=60) == 141
    assert b"Traceback" not in err
    assert b"BrokenPipeError" not in err


# The child waits for one byte on stdin before it runs the command, so the
# parent has closed its end of stdout before the command writes anything.
_GATED = (
    "import sys\n"
    "sys.stdin.buffer.read(1)\n"
    "from uripath.cli import main\n"
    "raise SystemExit(main(sys.argv[1:]))\n"
)


def _run_with_the_reader_gone(argv, stdin=b""):
    proc = subprocess.Popen(
        [sys.executable, "-c", _GATED, *argv],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_child_env(),
    )
    proc.stdout.close()
    try:
        proc.stdin.write(b"g" + stdin)
        proc.stdin.close()
    except OSError:
        pass  # The child exited before it read everything.
    try:
        err = proc.stderr.read()
        return proc.wait(timeout=60), err
    finally:
        proc.stderr.close()
        if not proc.stdin.closed:
            proc.stdin.close()


@pytest.mark.parametrize("size", [1, 64 * 1024, 3 * _MEBIBYTE])
def test_read_exits_141_when_stdout_closed_before_the_first_byte(size):
    status, err = _run_with_the_reader_gone(["read", "-"], stdin=b"z" * size)
    assert err == b""
    assert status == 141


def test_write_argument_exits_141_when_stdout_closed_before_the_first_byte():
    status, err = _run_with_the_reader_gone(["write", "-", "hello"])
    assert err == b""
    assert status == 141


def test_sync_dry_run_exits_141_when_stdout_closed_before_the_first_byte(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")
    status, err = _run_with_the_reader_gone(
        ["sync", "--dry-run", str(source), str(target)]
    )
    assert err == b""
    assert status == 141
    assert not (target / "a.txt").exists()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["nope"],
        ["read"],
        ["read", "a", "b"],
        ["write", "f", "x", "--encoding", "no-such-codec"],
        ["write", "f", "x", "--encoding", "hex"],
        ["cp", "a"],
        ["rm", "--no-such-flag", "a"],
        ["sync", "a"],
    ],
)
def test_a_wrong_invocation_returns_2_and_changes_nothing(
    argv, run, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    status, out, err = run(*argv, stdin=b"q")
    assert (status, out) == (2, b"")
    assert err.strip()
    assert list(tmp_path.iterdir()) == []


def test_the_unknown_encoding_is_named(run):
    status, _, err = run("write", "f", "x", "--encoding", "no-such-codec")
    assert status == 2
    assert "no-such-codec" in err


@pytest.fixture
def refused(monkeypatch):
    """Every connection is refused at once, as a loopback port with nothing
    listening on it does (Windows takes seconds to say so)."""
    import socket

    def connect(self, address):
        raise ConnectionRefusedError(errno.ECONNREFUSED, "refused")

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.mark.parametrize("scheme", ["ftp", "http", "dav"])
@pytest.mark.parametrize("command", ["read", "rm", "cp-from", "cp-to", "sync"])
def test_no_message_carries_the_password_of_a_uri(
    scheme, command, run, refused, tmp_path
):
    secret = "S3CRETVALUE"
    uri = f"{scheme}://user:{secret}@127.0.0.1:9/o/r/x"
    local = tmp_path / "local"
    local.mkdir()
    (local / "f").write_text("x", encoding="utf-8")
    argv = {
        "read": ["read", uri],
        "rm": ["rm", uri],
        "cp-from": ["cp", uri, str(local / "out")],
        "cp-to": ["cp", str(local / "f"), uri],
        "sync": ["sync", uri, str(local)],
    }[command]
    status, out, err = run(*argv)
    assert status == 1
    assert "Refused" in err or "refused" in err
    assert secret not in err and secret.encode() not in out
