import io
import json
import struct

import pytest

from native_host.protocol import MAX_MESSAGE_BYTES, ProtocolError, read_message, set_binary_stdio, write_message


def test_native_message_round_trip_uses_32_bit_native_endian_length():
    stream = io.BytesIO()
    payload = {"command": "status", "value": "✓"}

    write_message(stream, payload)
    raw = stream.getvalue()
    expected_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    assert raw[:4] == struct.pack("=I", len(expected_body))
    assert raw[4:] == expected_body
    stream.seek(0)
    assert read_message(stream) == payload


def test_native_message_eof_returns_none_and_truncated_frame_is_rejected():
    assert read_message(io.BytesIO(b"")) is None
    with pytest.raises(ProtocolError, match="header"):
        read_message(io.BytesIO(b"\x04\x00"))
    with pytest.raises(ProtocolError, match="payload"):
        read_message(io.BytesIO(struct.pack("=I", 4) + b"{}"))


def test_native_message_rejects_oversize_frame():
    raw = struct.pack("=I", MAX_MESSAGE_BYTES + 1)
    with pytest.raises(ProtocolError, match="too large"):
        read_message(io.BytesIO(raw))


def test_set_binary_stdio_switches_both_streams_to_binary_mode():
    calls = []

    class FakeStream:
        def __init__(self, fd):
            self.fd = fd
        def fileno(self):
            return self.fd

    set_binary_stdio(
        stdin=FakeStream(10),
        stdout=FakeStream(11),
        setmode=lambda fd, flag: calls.append((fd, flag)),
        binary_flag=1234,
    )

    assert calls == [(10, 1234), (11, 1234)]
