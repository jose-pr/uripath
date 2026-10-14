"""`copy_stream`: bytes between paths and binary streams, in chunks."""

from __future__ import annotations

import errno
import io

import pytest

import uripath
from pathapi.mempath import MemPath
from uripath import _transfer, copy_stream
from uripath.exceptions import OutputClosedError, URIPathError

_MEBIBYTE = 1024 * 1024
_BIG = bytes(range(256)) * (3 * _MEBIBYTE // 256 + 1)


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


class _ClosedPipe(io.BytesIO):
    def write(self, data):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    def flush(self):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")


class _InvalidArgumentPipe(io.BytesIO):
    """What a Windows pipe reports after its reader closed: EINVAL."""

    def write(self, data):
        raise OSError(errno.EINVAL, "Invalid argument")

    def flush(self):
        raise OSError(errno.EINVAL, "Invalid argument")


class _FlushFails(io.BytesIO):
    def flush(self):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")


def test_a_path_is_copied_to_a_stream(tmp_path):
    source = tmp_path / "in.bin"
    source.write_bytes(b"hello")
    target = io.BytesIO()
    copy_stream(source, target)
    assert target.getvalue() == b"hello"


def test_a_stream_is_copied_to_a_path_given_as_text(tmp_path):
    target = tmp_path / "out.bin"
    copy_stream(io.BytesIO(b"data"), str(target))
    assert target.read_bytes() == b"data"


def test_a_uri_is_a_path_like_any_other(tmp_path):
    source = tmp_path / "in.bin"
    source.write_bytes(b"over a uri")
    target = tmp_path / "out.bin"
    copy_stream(source.as_uri(), target.as_uri())
    assert target.read_bytes() == b"over a uri"


def test_a_stream_is_copied_to_a_stream():
    target = io.BytesIO()
    copy_stream(io.BytesIO(b"pipe"), target)
    assert target.getvalue() == b"pipe"


def test_a_path_object_of_the_core_is_copied(tmp_path):
    (tmp_path / "in.bin").write_bytes(b"x")
    memory = MemPath("/target")
    copy_stream(uripath.as_path(str(tmp_path / "in.bin")), memory)
    assert memory.read_bytes() == b"x"


def test_no_text_is_special_so_a_dash_names_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "-").write_bytes(b"a file called dash")
    out = io.BytesIO()
    copy_stream("-", out)
    assert out.getvalue() == b"a file called dash"


def test_streams_stay_open_and_the_target_is_flushed():
    class Flushed(io.BytesIO):
        flushes = 0

        def flush(self):
            self.flushes += 1
            super().flush()

    source, target = io.BytesIO(b"x"), Flushed()
    copy_stream(source, target)
    assert not source.closed and not target.closed
    assert target.flushes >= 1


def test_the_copy_goes_in_chunks_of_the_default_size(tmp_path):
    source = tmp_path / "big.bin"
    source.write_bytes(_BIG)
    target = _RecordingWriter()
    copy_stream(source, target)
    assert target.getvalue() == _BIG
    assert len(target.sizes) > 1
    assert max(target.sizes) <= _MEBIBYTE


def test_a_stream_is_read_in_chunks_of_the_default_size(tmp_path):
    reader = _RecordingReader(_BIG)
    out = tmp_path / "out.bin"
    copy_stream(reader, out)
    assert out.read_bytes() == _BIG
    assert reader.sizes and all(0 < size <= _MEBIBYTE for size in reader.sizes)


def test_the_chunk_size_is_the_caller_s(tmp_path):
    reader = _RecordingReader(b"x" * 1000)
    writer = _RecordingWriter()
    copy_stream(reader, writer, chunk_size=100)
    assert writer.getvalue() == b"x" * 1000
    assert max(writer.sizes) <= 100 and len(writer.sizes) == 10
    assert all(0 < size <= 100 for size in reader.sizes)


def test_exclusive_refuses_an_existing_target_and_keeps_it(tmp_path):
    target = tmp_path / "important.bin"
    target.write_bytes(b"precious")
    with pytest.raises(FileExistsError):
        copy_stream(io.BytesIO(b"clobbered"), target, exclusive=True)
    assert target.read_bytes() == b"precious"


def test_exclusive_creates_a_missing_target(tmp_path):
    target = tmp_path / "new.bin"
    copy_stream(io.BytesIO(b"fresh"), target, exclusive=True)
    assert target.read_bytes() == b"fresh"


def test_a_target_is_replaced_unless_exclusive(tmp_path):
    target = tmp_path / "t.bin"
    target.write_bytes(b"old, and longer")
    copy_stream(io.BytesIO(b"new"), target)
    assert target.read_bytes() == b"new"


def test_exclusive_does_not_apply_to_a_stream():
    target = io.BytesIO()
    target.write(b"already ")
    copy_stream(io.BytesIO(b"more"), target, exclusive=True)
    assert target.getvalue() == b"already more"


def test_a_missing_source_path_is_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        copy_stream(tmp_path / "missing", io.BytesIO())


@pytest.mark.parametrize("stream", [_ClosedPipe, _FlushFails])
def test_a_target_stream_whose_reader_went_away_is_output_closed(stream, tmp_path):
    source = tmp_path / "in.bin"
    source.write_bytes(b"x" * 100)
    with pytest.raises(OutputClosedError) as caught:
        copy_stream(source, stream())
    assert isinstance(caught.value, BrokenPipeError)
    assert isinstance(caught.value, URIPathError)
    assert caught.value.errno == errno.EPIPE


def test_einval_is_a_closed_pipe_where_windows_says_so(monkeypatch):
    monkeypatch.setattr(_transfer, "_WINDOWS", True)
    with pytest.raises(OutputClosedError):
        copy_stream(io.BytesIO(b"x"), _InvalidArgumentPipe())


def test_einval_is_an_error_of_its_own_elsewhere(monkeypatch):
    monkeypatch.setattr(_transfer, "_WINDOWS", False)
    with pytest.raises(OSError) as caught:
        copy_stream(io.BytesIO(b"x"), _InvalidArgumentPipe())
    assert not isinstance(caught.value, OutputClosedError)
    assert caught.value.errno == errno.EINVAL


def test_a_broken_pipe_of_the_source_is_not_output_closed():
    class Broken(io.BytesIO):
        def read(self, size=-1):
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    with pytest.raises(BrokenPipeError) as caught:
        copy_stream(Broken(), io.BytesIO())
    assert not isinstance(caught.value, OutputClosedError)


def test_a_broken_pipe_of_a_target_path_is_not_output_closed():
    class Remote(MemPath):
        def open(self, mode="r", *args, **kwargs):
            return _ClosedPipe()

    with pytest.raises(BrokenPipeError) as caught:
        copy_stream(io.BytesIO(b"x"), Remote("/t"))
    assert not isinstance(caught.value, OutputClosedError)


@pytest.mark.parametrize(
    ("source", "target"),
    [(42, io.BytesIO()), (io.BytesIO(b"x"), 42), (None, io.BytesIO())],
)
def test_what_is_neither_a_path_nor_a_stream_is_a_type_error(source, target):
    with pytest.raises(TypeError, match="binary stream"):
        copy_stream(source, target)


def test_the_root_exports_it():
    assert "copy_stream" in uripath.__all__
    assert uripath.copy_stream is copy_stream
