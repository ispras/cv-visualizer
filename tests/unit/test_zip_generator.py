#
# CVV is a continuous verification visualizer.
# Copyright (c) 2023 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Unit tests for web.ZipGenerator.ZipStream (streaming zip writer)."""

import io
import zipfile

from web.ZipGenerator import ZipStream, CHUNK_SIZE


def drain(gen):
    return b"".join(gen)


def open_zip(data):
    return zipfile.ZipFile(io.BytesIO(data))


def test_compress_string_roundtrip():
    stream = ZipStream()
    data = drain(stream.compress_string("hello.txt", "Hello, world")) + stream.close_stream()
    zf = open_zip(data)
    assert zf.namelist() == ["hello.txt"]
    assert zf.read("hello.txt") == b"Hello, world"
    assert zf.testzip() is None


def test_compress_string_accepts_bytes():
    stream = ZipStream()
    payload = b"\x00\x01\x02binary"
    data = drain(stream.compress_string("bin.dat", payload)) + stream.close_stream()
    assert open_zip(data).read("bin.dat") == payload


def test_compress_string_unicode_name_and_content():
    stream = ZipStream()
    data = drain(stream.compress_string("файл.txt", "привет")) + stream.close_stream()
    zf = open_zip(data)
    assert zf.namelist() == ["файл.txt"]
    assert zf.read("файл.txt").decode("utf8") == "привет"


def test_compress_file_roundtrip_small(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("file content", encoding="utf8")
    stream = ZipStream()
    data = drain(stream.compress_file(str(src), "src.txt")) + stream.close_stream()
    zf = open_zip(data)
    assert zf.read("src.txt") == b"file content"
    assert zf.testzip() is None


def test_compress_file_large_exceeds_chunk(tmp_path):
    payload = (b"abcdefgh" * (CHUNK_SIZE // 8 + 3))
    src = tmp_path / "big.bin"
    src.write_bytes(payload)
    stream = ZipStream()
    data = drain(stream.compress_file(str(src), "big.bin")) + stream.close_stream()
    assert open_zip(data).read("big.bin") == payload


def test_compress_buffer_roundtrip():
    stream = ZipStream()
    data = drain(stream.compress_buffer("buf.txt", io.BytesIO(b"buffer payload"))) + stream.close_stream()
    assert open_zip(data).read("buf.txt") == b"buffer payload"


def test_compress_buffer_reads_from_start_regardless_of_position():
    stream = ZipStream()
    buffer = io.BytesIO(b"buffer payload")
    buffer.seek(4)
    data = drain(stream.compress_buffer("buf.txt", buffer)) + stream.close_stream()
    assert open_zip(data).read("buf.txt") == b"buffer payload"


def test_compress_buffer_large_exceeds_chunk():
    payload = b"z" * (CHUNK_SIZE * 2 + 5)
    stream = ZipStream()
    data = drain(stream.compress_buffer("big.txt", io.BytesIO(payload))) + stream.close_stream()
    assert open_zip(data).read("big.txt") == payload


def test_compress_stream_roundtrip():
    stream = ZipStream()
    data = drain(stream.compress_stream("stream.bin", iter([b"one", b"two", b"three"])))
    data += stream.close_stream()
    assert open_zip(data).read("stream.bin") == b"onetwothree"


def test_compress_stream_skips_empty_chunks():
    stream = ZipStream()
    data = drain(stream.compress_stream("stream.bin", iter([b"a", b"", b"b"])))
    data += stream.close_stream()
    assert open_zip(data).read("stream.bin") == b"ab"


def test_multiple_entries_have_correct_offsets():
    stream = ZipStream()
    data = drain(stream.compress_string("first.txt", "1"))
    data += drain(stream.compress_string("second.txt", "2"))
    data += drain(stream.compress_string("third.txt", "3"))
    data += stream.close_stream()
    zf = open_zip(data)
    assert zf.namelist() == ["first.txt", "second.txt", "third.txt"]
    assert [zf.read(n) for n in zf.namelist()] == [b"1", b"2", b"3"]
    assert zf.testzip() is None


def test_close_stream_emits_central_directory_and_eocd():
    stream = ZipStream()
    drain(stream.compress_string("a.txt", "x"))
    footer = stream.close_stream()
    assert b"PK\x01\x02" in footer  # central directory header
    assert footer[-22:-18] == b"PK\x05\x06"  # end of central directory record


def test_close_stream_with_no_entries_is_valid_empty_zip():
    stream = ZipStream()
    data = stream.close_stream()
    zf = open_zip(data)
    assert zf.namelist() == []
