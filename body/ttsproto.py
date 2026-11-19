"""Pipe protocol between the body and its TTS worker (ADR-0018).

The worker runs Piper (GPL-3.0) in its own process, so nothing else in the body
imports it. Requests are JSON lines on the worker's stdin: {"id": "...", "text": "..."}.
Replies on its stdout are frames: one type byte, a 4-byte big-endian length, the data.

    R  ready     JSON {"sample_rate": int}           once, after loading the voice
    A  audio     signed 16-bit little-endian mono PCM, any number per request
    E  end       JSON {"id": str}                     the request is complete
    X  error     JSON {"id": str | null, "error": str}

Audio exists only in the pipe and in memory, never on disk (CLAUDE.md).
"""

import json
import struct
from typing import BinaryIO

READY, AUDIO, END, ERROR = b"R", b"A", b"E", b"X"
_HEADER = struct.Struct(">cI")
MAX_FRAME = 16 * 1024 * 1024


class ProtocolError(Exception):
    pass


def write_frame(stream: BinaryIO, kind: bytes, data: bytes) -> None:
    stream.write(_HEADER.pack(kind, len(data)) + data)
    stream.flush()


def write_json(stream: BinaryIO, kind: bytes, value: dict) -> None:
    write_frame(stream, kind, json.dumps(value, ensure_ascii=False).encode())


def _read_exact(stream: BinaryIO, n: int) -> bytes | None:
    chunks, got = [], 0
    while got < n:
        chunk = stream.read(n - got)
        if not chunk:
            return None
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> tuple[bytes, bytes] | None:
    """(kind, data), or None at the end of the stream."""
    header = _read_exact(stream, _HEADER.size)
    if header is None:
        return None
    kind, length = _HEADER.unpack(header)
    if kind not in (READY, AUDIO, END, ERROR) or length > MAX_FRAME:
        raise ProtocolError(f"bad frame header {header!r}")
    data = _read_exact(stream, length)
    if data is None:
        raise ProtocolError("stream ended inside a frame")
    return kind, data


def request(text_id: str, text: str) -> bytes:
    return (json.dumps({"id": text_id, "text": text}, ensure_ascii=False) + "\n").encode()
