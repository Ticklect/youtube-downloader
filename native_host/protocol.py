from __future__ import annotations

import json
import os
import struct
import sys
from typing import BinaryIO


MAX_MESSAGE_BYTES = 1024 * 1024


class ProtocolError(ValueError):
    pass


def read_message(stream: BinaryIO) -> dict | None:
    header = stream.read(4)
    if header == b"":
        return None
    if len(header) != 4:
        raise ProtocolError("Native Messaging header is truncated.")
    (length,) = struct.unpack("=I", header)
    if length > MAX_MESSAGE_BYTES:
        raise ProtocolError("Native Messaging payload is too large.")
    payload = stream.read(length)
    if len(payload) != length:
        raise ProtocolError("Native Messaging payload is truncated.")
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Native Messaging payload is not valid UTF-8 JSON.") from exc
    if not isinstance(message, dict):
        raise ProtocolError("Native Messaging payload must be a JSON object.")
    return message


def write_message(stream: BinaryIO, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Native Messaging response is too large.")
    stream.write(struct.pack("=I", len(body)))
    stream.write(body)
    stream.flush()


def set_binary_stdio(*, stdin=None, stdout=None, setmode=None, binary_flag=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    if setmode is None:
        import msvcrt
        setmode = msvcrt.setmode
    if binary_flag is None:
        binary_flag = os.O_BINARY
    setmode(stdin.fileno(), binary_flag)
    setmode(stdout.fileno(), binary_flag)
