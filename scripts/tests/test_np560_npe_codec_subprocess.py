"""Launch the DLL-free NPE codec service and exchange a real Unix-socket frame."""

from __future__ import annotations

import hashlib
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from scripts.serve_np560_npe_codec import OwnedMode5Codec, read_exact, serve_connection


SERVICE = Path(__file__).resolve().parents[1] / "serve_np560_npe_codec.py"
FIRST_FRAME = bytes.fromhex("488e2b000e1d3579d9a81be12ccb06057dd54c76ec")
FIRST_PCM_SHA256 = "7d68146ede3a8706cb01914eecad402abb653c7dbbd8681b0552b7d8d1c34a4f"


def test_failed_reinit_invalidates_previous_codec_stream() -> None:
    client, server = socket.socketpair()
    failure = []

    def run_server() -> None:
        try:
            with server:
                serve_connection(server, OwnedMode5Codec)
        except Exception as error:
            failure.append(error)

    worker = threading.Thread(target=run_server, daemon=True)
    worker.start()
    with client:
        client.settimeout(2)
        client.sendall(b"I\x05")
        assert read_exact(client, 3) == b"K\xa8\x00"
        client.sendall(b"I\x06")
        assert read_exact(client, 1) == b"E"
        length = struct.unpack("<H", read_exact(client, 2))[0]
        assert b"supports mode 5 only" in read_exact(client, length)
        client.sendall(b"D" + struct.pack("<H", 21) + FIRST_FRAME)
        assert read_exact(client, 1) == b"E"
        length = struct.unpack("<H", read_exact(client, 2))[0]
        assert read_exact(client, length) == b"decoder was not initialized"
        client.sendall(b"I\x05")
        assert read_exact(client, 3) == b"K\xa8\x00"
        client.sendall(b"D" + struct.pack("<H", 21) + FIRST_FRAME)
        reply = read_exact(client, 323)
        assert reply[:3] == b"P\xa0\x00"
        assert hashlib.sha256(reply[3:]).hexdigest() == FIRST_PCM_SHA256
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert not failure


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX"), reason="Unix sockets unavailable")
def test_owned_backend_serves_tianjiang_without_dll() -> None:
    with tempfile.TemporaryDirectory(prefix="npc-") as directory:
        endpoint = Path(directory) / "c.sock"
        process = subprocess.Popen(
            [sys.executable, str(SERVICE), "--backend", "owned",
             "--socket", str(endpoint)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while not endpoint.exists():
                if process.poll() is not None:
                    _, stderr = process.communicate()
                    pytest.fail(f"owned codec exited early: {stderr.decode(errors='replace')}")
                if time.monotonic() >= deadline:
                    pytest.fail("owned codec did not create its socket")
                time.sleep(0.01)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
                stream.settimeout(5)
                stream.connect(str(endpoint))
                stream.sendall(b"I\x05")
                assert read_exact(stream, 3) == b"K\xa8\x00"
                stream.sendall(b"D" + struct.pack("<H", 21) + FIRST_FRAME)
                reply = read_exact(stream, 323)
                assert reply[:3] == b"P\xa0\x00"
                assert hashlib.sha256(reply[3:]).hexdigest() == FIRST_PCM_SHA256
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
